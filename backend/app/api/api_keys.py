import httpx
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db
from app.api.auth import get_current_user
from app.schemas.auth import UserOut
from app.schemas.api_key import ApiKeyCreate, ApiKeyOut
from app.models.user import ApiKey
from app.core.security import encrypt_api_key, decrypt_api_key

router = APIRouter(prefix="/api-keys", tags=["API Keys"])

async def verify_provider_api_key(provider_name: str, api_key: str) -> bool:
    provider = provider_name.lower().strip()

    if provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    return True
                else:
                    detail = "Invalid key"
                    try:
                        err_json = res.json()
                        detail = err_json.get("error", {}).get("message", detail)
                    except:
                        pass
                    raise HTTPException(status_code=400, detail=f"Gemini API verification failed: {detail}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=400, detail=f"Could not connect to Gemini API: {str(e)}")

    elif provider == "groq":
        url = "https://api.groq.com/openai/v1/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    return True
                else:
                    detail = "Invalid key"
                    try:
                        err_json = res.json()
                        detail = err_json.get("error", {}).get("message", detail)
                    except:
                        pass
                    raise HTTPException(status_code=400, detail=f"Groq API verification failed: {detail}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=400, detail=f"Could not connect to Groq API: {str(e)}")

    elif provider == "openrouter":
        url = "https://openrouter.ai/api/v1/auth/key"
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    return True
                else:
                    detail = "Invalid key"
                    try:
                        err_json = res.json()
                        detail = err_json.get("error", {}).get("message", detail)
                    except:
                        pass
                    raise HTTPException(status_code=400, detail=f"OpenRouter API verification failed: {detail}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=400, detail=f"Could not connect to OpenRouter API: {str(e)}")

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_name}")


@router.get("", response_model=List[ApiKeyOut])
async def list_api_keys(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id)
    )
    db_keys = result.scalars().all()
    
    out_keys = []
    for k in db_keys:
        try:
            raw_key = decrypt_api_key(k.encrypted_key)
        except Exception:
            raw_key = k.encrypted_key

        masked_key = ""
        if len(raw_key) > 8:
            # Safely mask the key
            masked_key = f"{raw_key[:4]}...{raw_key[-4:]}"
        else:
            masked_key = "****"

        out_keys.append(ApiKeyOut(
            provider_name=k.provider_name,
            masked_key=masked_key,
            created_at=k.created_at
        ))
    return out_keys


@router.post("", response_model=ApiKeyOut, status_code=status.HTTP_201_CREATED)
async def save_api_key(
    schema: ApiKeyCreate,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    provider_name = schema.provider_name.lower().strip()
    if provider_name not in ["gemini", "groq", "openrouter"]:
        raise HTTPException(status_code=400, detail="Unsupported provider name.")

    # Verify the key
    await verify_provider_api_key(provider_name, schema.api_key)

    # Check if existing key
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id, ApiKey.provider_name == provider_name)
    )
    existing_key = result.scalars().first()

    # Encrypt key
    encrypted_val = encrypt_api_key(schema.api_key)

    if existing_key:
        existing_key.encrypted_key = encrypted_val
        db.add(existing_key)
        db_key = existing_key
    else:
        db_key = ApiKey(
            user_id=current_user.id,
            provider_name=provider_name,
            encrypted_key=encrypted_val
        )
        db.add(db_key)

    await db.commit()
    await db.refresh(db_key)

    # Mask key
    raw_key = schema.api_key
    masked_key = ""
    if len(raw_key) > 8:
        masked_key = f"{raw_key[:4]}...{raw_key[-4:]}"
    else:
        masked_key = "****"

    return ApiKeyOut(
        provider_name=db_key.provider_name,
        masked_key=masked_key,
        created_at=db_key.created_at
    )


@router.delete("/{provider_name}")
async def delete_api_key(
    provider_name: str,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    provider_name = provider_name.lower().strip()
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id, ApiKey.provider_name == provider_name)
    )
    existing_key = result.scalars().first()
    if not existing_key:
        raise HTTPException(status_code=404, detail="API key not found.")

    await db.delete(existing_key)
    await db.commit()
    return {"detail": f"API key for {provider_name} successfully deleted."}
