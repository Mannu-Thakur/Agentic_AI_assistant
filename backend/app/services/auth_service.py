from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from app.models.user import User, UserPreference
from app.schemas.auth import UserRegister
from app.core.security import get_password_hash, verify_password, blacklist_token
from app.core.config import settings

class AuthService:
    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalars().first()

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalars().first()

    @staticmethod
    async def create_user(db: AsyncSession, schema: UserRegister) -> User:
        # Check if user already exists
        existing_user = await AuthService.get_user_by_email(db, schema.email)
        if existing_user:
            raise ValueError("Email already registered")

        # Create user record
        hashed = get_password_hash(schema.password)
        new_user = User(
            email=schema.email,
            hashed_password=hashed,
            full_name=schema.full_name,
        )
        db.add(new_user)
        try:
            await db.flush()  # Flush to get user id
        except IntegrityError:
            await db.rollback()
            raise ValueError("Email already registered")

        # Create standard preference profile
        new_prefs = UserPreference(
            user_id=new_user.id
        )
        db.add(new_prefs)
        await db.commit()
        await db.refresh(new_user)
        return new_user

    @staticmethod
    async def authenticate_user(db: AsyncSession, email: str, plain_password: str) -> Optional[User]:
        user = await AuthService.get_user_by_email(db, email)
        if not user or not user.hashed_password:
            return None
        if not verify_password(plain_password, user.hashed_password):
            return None
        return user

    @staticmethod
    async def update_user_password(db: AsyncSession, user_id: str, new_password: str) -> bool:
        user = await AuthService.get_user_by_id(db, user_id)
        if not user:
            return False
        user.hashed_password = get_password_hash(new_password)
        await db.commit()
        try:
            await db.refresh(user)
        except Exception:
            pass

        # NEW-HIGH-2 FIX: Invalidate all active tokens upon password change.
        # If this fails, old tokens remain valid — log at ERROR so ops can react.
        try:
            await blacklist_token(f"user_revoked:{user_id}", settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)
        except Exception as _bl_err:
            import logging as _log
            _log.getLogger("app.services.auth_service").error(
                f"[SECURITY] Failed to blacklist tokens for user {user_id} after password change: {_bl_err}. "
                "Old tokens may remain valid until natural expiry."
            )
        return True


