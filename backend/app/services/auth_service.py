from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User, UserPreference
from app.schemas.auth import UserRegister
from app.core.security import get_password_hash, verify_password

class AuthService:
    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        result = await db.execute(select(User).filter(User.email == email))
        return result.scalars().first()

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
        result = await db.execute(select(User).filter(User.id == user_id))
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
        await db.flush()  # Flush to get user id

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
        await db.refresh(user)
        return True

