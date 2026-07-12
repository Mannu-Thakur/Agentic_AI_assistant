from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, verify_token
from app.schemas.auth import UserRegister, UserLogin, Token, UserOut
from app.services.auth_service import AuthService
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> UserOut:
    token = credentials.credentials
    user_id = verify_token(token, "access")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user

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
    db: AsyncSession = Depends(get_db)
):
    user = await AuthService.authenticate_user(db, schema.email, schema.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
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
        secure=False,   
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
    
    user_id = verify_token(refresh_token, "refresh")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
        
    user = await AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
        
    access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)
    
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        samesite="lax",
        secure=False,
    )
    
    return Token(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@router.get("/me", response_model=UserOut)
async def get_me(current_user: UserOut = Depends(get_current_user)):
    return current_user

@router.get("/oauth/google")
async def google_login():
    """
    Redirects the user to Google OAuth consent screen.
    In local development, returns a mock consent URL or redirects.
    """
    # Placeholder for google auth client initiation
    redirect_uri = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID or "mock_client_id",
        "redirect_uri": "http://localhost:5173/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
    }
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return {"url": f"{redirect_uri}?{query_string}"}

@router.post("/oauth/google/callback", response_model=Token)
async def google_callback(code: str, response: Response, db: AsyncSession = Depends(get_db)):
    """
    Exchanges authorization code for Google profile data,
    creates user if they don't exist, and issues JWT access/refresh tokens.
    """
    # Mocking successful OAuth authentication if keys are missing
    mock_email = "oauth_google_user@example.com"
    mock_name = "Google OAuth User"
    
    # In production, query Google APIs to get user profile:
    # user_profile = await exchange_code_for_profile(code)
    
    user = await AuthService.get_user_by_email(db, mock_email)
    if not user:
        # Create user without password (OAuth user)
        user = User(
            email=mock_email,
            full_name=mock_name,
            avatar_url="https://lh3.googleusercontent.com/a/default-user"
        )
        db.add(user)
        await db.flush()
        
        # Create standard preference profile
        new_prefs = UserPreference(user_id=user.id)
        db.add(new_prefs)
        await db.commit()
        await db.refresh(user)
        
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        samesite="lax",
        secure=False,
    )
    
    return Token(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@router.get("/oauth/github")
async def github_login():
    """
    Redirects the user to GitHub OAuth consent screen.
    """
    redirect_uri = "https://github.com/login/oauth/authorize"
    params = {
        "client_id": settings.GITHUB_CLIENT_ID or "mock_client_id",
        "redirect_uri": "http://localhost:5173/auth/github/callback",
        "scope": "user:email",
    }
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return {"url": f"{redirect_uri}?{query_string}"}

@router.post("/oauth/github/callback", response_model=Token)
async def github_callback(code: str, response: Response, db: AsyncSession = Depends(get_db)):
    """
    Exchanges code for GitHub profile and logs user in.
    """
    mock_email = "oauth_github_user@example.com"
    mock_name = "GitHub OAuth User"
    
    user = await AuthService.get_user_by_email(db, mock_email)
    if not user:
        user = User(
            email=mock_email,
            full_name=mock_name,
            avatar_url="https://github.com/identicons/default-user"
        )
        db.add(user)
        await db.flush()
        
        new_prefs = UserPreference(user_id=user.id)
        db.add(new_prefs)
        await db.commit()
        await db.refresh(user)
        
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        samesite="lax",
        secure=False,
    )
    
    return Token(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

