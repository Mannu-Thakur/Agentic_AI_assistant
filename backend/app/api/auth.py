import httpx
from typing import Optional
from datetime import timedelta
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, verify_token
from app.schemas.auth import UserRegister, UserLogin, Token, UserOut, ForgotPasswordRequest, ResetPasswordRequest
from app.services.auth_service import AuthService
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.models.user import User, UserPreference

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> UserOut:
    token = credentials.credentials
    from app.core.security import is_token_blacklisted
    from app.services.audit_service import AuditService
    client_ip = request.client.host if request.client else "unknown"

    if await is_token_blacklisted(token):
        await AuditService.log_event(db, None, "permission_failure", {"reason": "blacklisted_token"}, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user_id = verify_token(token, "access")
    if not user_id:
        await AuditService.log_event(db, None, "permission_failure", {"reason": "invalid_or_expired_token"}, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Check if user session has been revoked globally (compromise circuit breaker)
    if await is_token_blacklisted(f"user_revoked:{user_id}"):
        await AuditService.log_event(db, user_id, "permission_failure", {"reason": "session_globally_revoked"}, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User session has been revoked due to security incident",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user = await AuthService.get_user_by_id(db, user_id)
    if not user:
        await AuditService.log_event(db, None, "permission_failure", {"reason": "user_not_found", "user_id": user_id}, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


class RoleChecker:
    """Dependency checker to enforce RBAC permissions (User, Moderator, Admin)."""
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: UserOut = Depends(get_current_user)):
        if getattr(current_user, "role", "user") not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions."
            )
        return current_user


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(schema: UserRegister, db: AsyncSession = Depends(get_db)):
    try:
        user = await AuthService.create_user(db, schema)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/login", response_model=Token)
async def login(
    schema: UserLogin,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    user = await AuthService.authenticate_user(db, schema.email, schema.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Audit log the login
    from app.services.audit_service import AuditService
    client_ip = request.client.host if request.client else "unknown"
    await AuditService.log_event(db, user.id, "login", {"method": "password"}, client_ip)

    # Clear any global user revocation marker upon successful primary authentication
    from app.core.security import unblacklist_token, blacklist_token
    await unblacklist_token(f"user_revoked:{user.id}")

    # Token rotation: blacklist old refresh token if exists
    old_refresh = request.cookies.get("refresh_token")
    if old_refresh:
        await blacklist_token(old_refresh, settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    access_token = create_access_token(user.id, expires_delta=access_token_expires)
    refresh_token = create_refresh_token(user.id, expires_delta=refresh_token_expires)
    
    # Set Refresh Token in HTTP-Only cookie for security
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        samesite="lax",
        secure=request.url.scheme == "https" or settings.ENVIRONMENT in ("staging", "production"),   
    )
    
    return Token(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@router.post("/refresh", response_model=Token)
async def refresh_token(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token"
        )
    
    from app.core.security import is_token_blacklisted, blacklist_token
    if await is_token_blacklisted(refresh_token):
        # Compromise detection: try to identify the user to invalidate all their active sessions
        try:
            from jose import jwt
            # Decode without validating expiration or audience to find the subject
            payload = jwt.decode(
                refresh_token, 
                settings.SECRET_KEY, 
                algorithms=[settings.ALGORITHM], 
                options={"verify_exp": False, "verify_aud": False}
            )
            user_id = payload.get("sub")
            if user_id:
                # Blacklist a user-revocation marker to invalidate all their tokens
                await blacklist_token(f"user_revoked:{user_id}", settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)
                from main import logger
                logger.warning(f"Replay attack detected on rotated refresh token! Revoking all sessions for user {user_id}")
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked"
        )

    user_id = verify_token(refresh_token, "refresh")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
        
    # Check if the user session has been globally revoked
    if await is_token_blacklisted(f"user_revoked:{user_id}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User session has been revoked due to security incident"
        )
        
    user = await AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
        
    # Blacklist the old refresh token as we rotate it
    await blacklist_token(refresh_token, settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)


    access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)
    
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        samesite="lax",
        secure=request.url.scheme == "https" or settings.ENVIRONMENT in ("staging", "production"),
    )
    
    return Token(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@router.get("/me", response_model=UserOut)
async def get_me(current_user: UserOut = Depends(get_current_user)):
    return current_user

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """Logs out the current user, blacklisting both access and refresh tokens."""
    auth_header = request.headers.get("Authorization")
    refresh_token = request.cookies.get("refresh_token")
    
    user_id = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        user_id = verify_token(token, "access")
        from app.core.security import blacklist_token
        await blacklist_token(token, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        
    if refresh_token:
        from app.core.security import blacklist_token
        await blacklist_token(refresh_token, settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)

    from app.services.audit_service import AuditService
    client_ip = request.client.host if request.client else "unknown"
    await AuditService.log_event(db, user_id, "logout", {}, client_ip)

    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        samesite="lax",
        secure=True if not settings.ENABLE_MOCK_OAUTH else False
    )
    return {"detail": "Successfully logged out."}

@router.get("/oauth/google")
async def google_login(redirect_uri: Optional[str] = None):
    """
    Redirects the user to Google OAuth consent screen.
    In local development, returns a mock consent URL or redirects.
    """
    from app.core.security import generate_state_token, store_oauth_state, is_safe_redirect_url
    if redirect_uri and not is_safe_redirect_url(redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The redirect_uri is not whitelisted. Open redirect blocked."
        )

    state = generate_state_token()
    await store_oauth_state(state)

    redirect_target = redirect_uri or settings.GOOGLE_REDIRECT_URI
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google OAuth is not configured on this server. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env."
        )

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_target,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return {"url": f"{auth_url}?{urlencode(params)}"}


@router.get("/oauth/google/callback", response_model=Token)
async def google_callback(
    code: str,
    response: Response,
    request: Request,
    state: Optional[str] = None,
    redirect_uri: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Exchanges authorization code for Google profile data,
    creates user if they don't exist, and issues JWT access/refresh tokens.
    """
    from app.core.security import verify_oauth_state, is_safe_redirect_url
    from app.services.audit_service import AuditService
    client_ip = request.client.host if request.client else "unknown"
    
    if redirect_uri and not is_safe_redirect_url(redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The redirect_uri is not whitelisted. Open redirect blocked."
        )

    if not state or not await verify_oauth_state(state):
        await AuditService.log_event(db, None, "oauth_failure", {"provider": "google", "reason": "Invalid or missing OAuth state"}, client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid OAuth state parameter. Possible CSRF attempt."
        )

    redirect_target = redirect_uri or settings.GOOGLE_REDIRECT_URI

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google OAuth is not configured on this server. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env."
        )

    if code.startswith("mock_"):
        profile = {
            "email": "mockuser@example.com",
            "name": "Mock User",
            "email_verified": True,
            "picture": "https://example.com/avatar.png"
        }
    else:
        # Google OAuth token exchange — FIX-2: 10s timeout on all external calls
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_target,
            "grant_type": "authorization_code"
        }

        async with httpx.AsyncClient(timeout=10.0) as google_client:  # FIX-5: renamed to avoid shadowing
            try:
                token_res = await google_client.post(token_url, data=token_data)
                if token_res.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Google OAuth token exchange failed: {token_res.text}"
                    )
                token_json = token_res.json()
                google_access_token = token_json.get("access_token")  # FIX-5: distinct name

                # Fetch user profile
                profile_url = "https://www.googleapis.com/oauth2/v3/userinfo"
                profile_res = await google_client.get(
                    profile_url,
                    headers={"Authorization": f"Bearer {google_access_token}"}
                )
                if profile_res.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to fetch Google profile info: {profile_res.text}"
                    )
                profile = profile_res.json()
            except httpx.TimeoutException:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Google API timed out. Please try again."
                )
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Could not connect to Google API: {str(e)}"
                )

    email = profile.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google profile did not contain a valid email."
        )
    # FIX-4: Require verified email from Google
    if not profile.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account email is not verified. Please verify your Google email first."
        )
    name = profile.get("name")
    avatar_url = profile.get("picture")
    
    # FIX-6: Race-safe get-or-create — use AuthService to prevent duplicate email on concurrent requests
    user = await AuthService.get_user_by_email(db, email)
    if not user:
        try:
            user = User(
                email=email,
                full_name=name,
                avatar_url=avatar_url
            )
            db.add(user)
            await db.flush()
            new_prefs = UserPreference(user_id=user.id)
            db.add(new_prefs)
            await db.commit()
            await db.refresh(user)
        except Exception:
            await db.rollback()
            # Another request may have created the user concurrently — retry lookup
            user = await AuthService.get_user_by_email(db, email)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user account."
                )
    else:
        # Update avatar/name if changed (existing OAuth user re-login)
        changed = False
        if name and user.full_name != name:
            user.full_name = name
            changed = True
        if avatar_url and user.avatar_url != avatar_url:
            user.avatar_url = avatar_url
            changed = True
        if changed:
            await db.commit()
            await db.refresh(user)
    await AuditService.log_event(db, user.id, "login", {"method": "oauth_google"}, client_ip)

    # Token rotation: blacklist old refresh token if exists
    old_refresh = request.cookies.get("refresh_token")
    if old_refresh:
        from app.core.security import blacklist_token
        await blacklist_token(old_refresh, settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        samesite="lax",
        secure=True if not settings.ENABLE_MOCK_OAUTH else False,
    )
    
    return Token(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@router.get("/oauth/github")
async def github_login(redirect_uri: Optional[str] = None):
    """
    Redirects the user to GitHub OAuth consent screen.
    """
    from app.core.security import generate_state_token, store_oauth_state
    from urllib.parse import urlencode
    state = generate_state_token()
    await store_oauth_state(state)

    redirect_target = redirect_uri or settings.GITHUB_REDIRECT_URI
    if not settings.GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub OAuth is not configured on this server. Please set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env."
        )

    auth_url = "https://github.com/login/oauth/authorize"
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": redirect_target,
        "scope": "user:email read:user",
        "state": state,
    }
    return {"url": f"{auth_url}?{urlencode(params)}"}


@router.get("/oauth/github/callback", response_model=Token)
async def github_callback(
    code: str,
    response: Response,
    request: Request,
    state: Optional[str] = None,
    redirect_uri: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Exchanges code for GitHub profile and logs user in.
    """
    from app.core.security import verify_oauth_state
    from app.services.audit_service import AuditService
    client_ip = request.client.host if request.client else "unknown"

    if not state or not await verify_oauth_state(state):
        await AuditService.log_event(db, None, "oauth_failure", {"provider": "github", "reason": "Invalid or missing OAuth state"}, client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid OAuth state parameter. Possible CSRF attempt."
        )
    redirect_target = redirect_uri or settings.GITHUB_REDIRECT_URI

    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub OAuth is not configured on this server. Please set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env."
        )

    if code.startswith("mock_"):
        profile = {
            "email": "mockgithub@example.com",
            "name": "Mock GitHub User",
            "login": "mockuser",
            "avatar_url": "https://example.com/avatar.png"
        }
        email = profile["email"]
    else:
        # GitHub OAuth token exchange
        token_url = "https://github.com/login/oauth/access_token"
        token_headers = {"Accept": "application/json"}
        token_data = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_target
        }
        
        # FIX-2: 10s timeout; FIX-5: renamed to avoid shadowing
        async with httpx.AsyncClient(timeout=10.0) as github_client:
            try:
                token_res = await github_client.post(token_url, data=token_data, headers=token_headers)
                if token_res.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"GitHub OAuth token exchange failed: {token_res.text}"
                    )
                token_json = token_res.json()
                github_access_token = token_json.get("access_token")  # FIX-5: distinct name
                if not github_access_token:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"GitHub OAuth error: {token_json.get('error_description', 'No access token returned')}"
                    )

                # Fetch user profile
                profile_url = "https://api.github.com/user"
                profile_headers = {
                    "Authorization": f"Bearer {github_access_token}",
                    "User-Agent": "Flagship-Agentic-AI-Workspace"
                }
                profile_res = await github_client.get(profile_url, headers=profile_headers)
                if profile_res.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to fetch GitHub profile info: {profile_res.text}"
                    )
                profile = profile_res.json()

                email = profile.get("email")
                # Fetch email from private emails list if profile returns null email
                if not email:
                    emails_url = "https://api.github.com/user/emails"
                    emails_res = await github_client.get(emails_url, headers=profile_headers)
                    if emails_res.status_code == 200:
                        emails_data = emails_res.json()
                        for em in emails_data:
                            if em.get("primary") and em.get("verified"):
                                email = em.get("email")
                                break
                        if not email and emails_data:
                            email = emails_data[0].get("email")
            except httpx.TimeoutException:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="GitHub API timed out. Please try again."
                )
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Could not connect to GitHub API: {str(e)}"
                )
                
    if not email:
        email = f"{profile.get('login')}@users.noreply.github.com"
        
    name = profile.get("name") or profile.get("login")
    avatar_url = profile.get("avatar_url")
    
    # FIX-6: Race-safe get-or-create
    user = await AuthService.get_user_by_email(db, email)
    if not user:
        try:
            user = User(
                email=email,
                full_name=name,
                avatar_url=avatar_url
            )
            db.add(user)
            await db.flush()
            new_prefs = UserPreference(user_id=user.id)
            db.add(new_prefs)
            await db.commit()
            await db.refresh(user)
        except Exception:
            await db.rollback()
            user = await AuthService.get_user_by_email(db, email)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user account."
                )
    else:
        changed = False
        if name and user.full_name != name:
            user.full_name = name
            changed = True
        if avatar_url and user.avatar_url != avatar_url:
            user.avatar_url = avatar_url
            changed = True
        if changed:
            await db.commit()
            await db.refresh(user)

    # Audit log the login
    from app.services.audit_service import AuditService
    client_ip = request.client.host if request.client else "unknown"
    await AuditService.log_event(db, user.id, "login", {"method": "oauth_github"}, client_ip)

    # Token rotation: blacklist old refresh token if exists
    old_refresh = request.cookies.get("refresh_token")
    if old_refresh:
        from app.core.security import blacklist_token
        await blacklist_token(old_refresh, settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        samesite="lax",
        secure=True if not settings.ENABLE_MOCK_OAUTH else False,
    )
    
    return Token(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/verify-reset-token", status_code=status.HTTP_200_OK)
async def verify_token_status(
    token: str = Query(..., description="Password reset token to verify")
):
    """
    Verifies if a password reset token is active and valid in real-time without consuming it.
    Returns 200 OK with {"valid": true} if valid, or 400 Bad Request if invalid/expired.
    """
    from app.core.security import verify_reset_token

    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is required."
        )

    is_valid = await verify_reset_token(token)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token. Please request a new password reset link."
        )

    return {"valid": True, "detail": "Token is valid and active."}


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    schema: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Sends a password reset link to the user's email if registered.
    Always returns a generic success message to prevent user enumeration attacks.
    Rate-limited to 3 requests per 15 minutes per email address.
    """
    import secrets
    from urllib.parse import urlparse
    from app.core.security import check_reset_rate_limit, store_reset_token
    from app.services.email_service import EmailService
    from app.services.audit_service import AuditService

    client_ip = request.client.host if request.client else "unknown"

    # Enforce rate limiting
    is_allowed = await check_reset_rate_limit(schema.email)
    if not is_allowed:
        await AuditService.log_event(db, None, "password_reset_rate_limited", {"email": schema.email}, client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many password reset requests for this email. Please try again in 15 minutes."
        )

    # Determine base frontend URL dynamically from request headers if available to prevent port/domain mismatch
    base_url = settings.FRONTEND_URL.rstrip('/')
    raw_origin = request.headers.get("origin") or request.headers.get("referer")
    if raw_origin:
        parsed = urlparse(raw_origin)
        if parsed.scheme and parsed.netloc:
            base_url = f"{parsed.scheme}://{parsed.netloc}"

    # User lookup
    user = await AuthService.get_user_by_email(db, schema.email)
    if user and user.hashed_password:
        # Generate token & store in Redis / memory fallback with TTL
        token = secrets.token_urlsafe(32)
        ttl_seconds = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES * 60
        await store_reset_token(token, user.id, ttl_seconds)

        # Build reset link
        reset_url = f"{base_url}/reset-password?token={token}"

        # Send email asynchronously
        await EmailService.send_password_reset_email(user.email, reset_url)
        await AuditService.log_event(db, user.id, "password_reset_requested", {"email": user.email}, client_ip)
    else:
        # User not found or OAuth-only user — log silently, don't disclose to client
        await AuditService.log_event(db, None, "password_reset_requested_unknown_email", {"email": schema.email}, client_ip)

    return {"detail": "If an account exists with that email, a password reset link has been sent."}



@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    schema: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Validates single-use reset token and updates the user's password.
    Also invalidates all active sessions for the user for security.
    """
    from app.core.security import verify_and_consume_reset_token, blacklist_token
    from app.services.audit_service import AuditService

    client_ip = request.client.host if request.client else "unknown"

    if len(schema.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long."
        )

    user_id = await verify_and_consume_reset_token(schema.token)
    if not user_id:
        await AuditService.log_event(db, None, "password_reset_invalid_token", {}, client_ip)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token. Please request a new password reset link."
        )

    updated = await AuthService.update_user_password(db, user_id, schema.new_password)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found."
        )

    # Invalidate all active sessions (compromise circuit breaker pattern)
    await blacklist_token(f"user_revoked:{user_id}", settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)

    await AuditService.log_event(db, user_id, "password_reset_completed", {}, client_ip)

    return {"detail": "Password has been reset successfully. You can now log in with your new password."}



