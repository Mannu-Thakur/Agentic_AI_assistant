import httpx
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, verify_token
from app.schemas.auth import UserRegister, UserLogin, Token, UserOut
from app.services.auth_service import AuthService
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.models.user import User, UserPreference

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
    if settings.ENABLE_MOCK_OAUTH:
        return {"url": f"{settings.GOOGLE_REDIRECT_URI}?code=mock_google_code"}
        
    # Placeholder for google auth client initiation
    redirect_uri = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID or "mock_client_id",
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
    }
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return {"url": f"{redirect_uri}?{query_string}"}

@router.get("/oauth/google/callback", response_model=Token)
async def google_callback(code: str, response: Response, db: AsyncSession = Depends(get_db)):
    """
    Exchanges authorization code for Google profile data,
    creates user if they don't exist, and issues JWT access/refresh tokens.
    """
    if settings.ENABLE_MOCK_OAUTH or code == "mock_google_code":
        email = "mock_google_user@example.com"
        name = "Mock Google User"
        avatar_url = None
    else:
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google OAuth is not configured on this server."
            )

        # Google OAuth token exchange
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                token_res = await client.post(token_url, data=token_data)
                if token_res.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Google OAuth token exchange failed: {token_res.text}"
                    )
                token_json = token_res.json()
                access_token = token_json.get("access_token")
                
                # Fetch user profile
                profile_url = "https://www.googleapis.com/oauth2/v3/userinfo"
                profile_res = await client.get(profile_url, headers={"Authorization": f"Bearer {access_token}"})
                if profile_res.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to fetch Google profile info: {profile_res.text}"
                    )
                profile = profile_res.json()
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Could not connect to Google API: {str(e)}"
                )

        email = profile.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google profile did not contain a valid email."
            )
        name = profile.get("name")
        avatar_url = profile.get("picture")
    
    user = await AuthService.get_user_by_email(db, email)
    if not user:
        # Create user without password (OAuth user)
        user = User(
            email=email,
            full_name=name,
            avatar_url=avatar_url
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
    if settings.ENABLE_MOCK_OAUTH:
        return {"url": f"{settings.GITHUB_REDIRECT_URI}?code=mock_github_code"}
        
    redirect_uri = "https://github.com/login/oauth/authorize"
    params = {
        "client_id": settings.GITHUB_CLIENT_ID or "mock_client_id",
        "redirect_uri": settings.GITHUB_REDIRECT_URI,
        "scope": "user:email",
    }
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return {"url": f"{redirect_uri}?{query_string}"}

@router.get("/oauth/github/callback", response_model=Token)
async def github_callback(code: str, response: Response, db: AsyncSession = Depends(get_db)):
    """
    Exchanges code for GitHub profile and logs user in.
    """
    if settings.ENABLE_MOCK_OAUTH or code == "mock_github_code":
        email = "mock_github_user@example.com"
        name = "Mock GitHub User"
        avatar_url = None
    else:
        if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub OAuth is not configured on this server."
            )

        # GitHub OAuth token exchange
        token_url = "https://github.com/login/oauth/access_token"
        token_headers = {"Accept": "application/json"}
        token_data = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.GITHUB_REDIRECT_URI
        }
        
        async with httpx.AsyncClient() as client:
            try:
                token_res = await client.post(token_url, data=token_data, headers=token_headers)
                if token_res.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"GitHub OAuth token exchange failed: {token_res.text}"
                    )
                token_json = token_res.json()
                access_token = token_json.get("access_token")
                if not access_token:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"GitHub OAuth error: {token_json.get('error_description', 'No access token returned')}"
                    )
                    
                # Fetch user profile
                profile_url = "https://api.github.com/user"
                profile_headers = {
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": "Flagship-Agentic-AI-Workspace"
                }
                profile_res = await client.get(profile_url, headers=profile_headers)
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
                    emails_res = await client.get(emails_url, headers=profile_headers)
                    if emails_res.status_code == 200:
                        emails = emails_res.json()
                        for em in emails:
                            if em.get("primary"):
                                email = em.get("email")
                                break
                        if not email and emails:
                            email = emails[0].get("email")
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Could not connect to GitHub API: {str(e)}"
                )
                
        if not email:
            email = f"{profile.get('login')}@users.noreply.github.com"
            
        name = profile.get("name") or profile.get("login")
        avatar_url = profile.get("avatar_url")
    
    user = await AuthService.get_user_by_email(db, email)
    if not user:
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

