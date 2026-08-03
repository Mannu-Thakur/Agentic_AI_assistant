import httpx
import json
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func
from app.core.database import get_db
from app.api.auth import get_current_user
from app.schemas.auth import UserOut
from app.schemas.api_key import ApiKeyCreate, ApiKeyOut, ProviderOut
from app.models.user import ApiKey
from app.core.security import encrypt_api_key, decrypt_api_key

router = APIRouter(prefix="/api-keys", tags=["API Keys"])
providers_router = APIRouter(prefix="/providers", tags=["Providers"])

class ApiKeyAuthError(Exception):
    """Raised when an API key is explicitly rejected by the provider due to invalid credentials."""
    pass

class ApiKeyNetworkError(Exception):
    """Raised when provider API check fails due to transient network or server reachability issues."""
    pass

# ─── Live Provider Verification & Model Fetching ───────────────────────────────────

async def verify_google(api_key: str) -> List[str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                models = []
                for m in data.get("models", []):
                    name = m.get("name", "")
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        if name.startswith("models/"):
                            name = name[len("models/"):]
                        models.append(name)
                return models
            else:
                detail = "Invalid key"
                try:
                    err_json = res.json()
                    detail = err_json.get("error", {}).get("message", detail)
                except:
                    pass
                if res.status_code in (400, 401, 403) or "API key not valid" in detail or "invalid" in detail.lower():
                    raise ApiKeyAuthError(
                        f"Google/Gemini API verification failed: {detail}. "
                        "Make sure: (1) the key is copied correctly with no extra spaces, "
                        "(2) the 'Generative Language API' is enabled in your Google Cloud Console, "
                        "(3) the key has no API restrictions blocking it."
                    )
                raise ApiKeyNetworkError(f"Google/Gemini API server error ({res.status_code}): {detail}")
    except httpx.RequestError as e:
        raise ApiKeyNetworkError(f"Could not connect to Google API: {str(e)}")

async def verify_openai(api_key: str) -> List[str]:
    url = "https://api.openai.com/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                models = [
                    m["id"] for m in data.get("data", [])
                    if not any(x in m["id"].lower() for x in ["whisper", "tts", "embed", "dall-e", "moderation", "babbage", "davinci"])
                ]
                return models
            else:
                detail = "Invalid key"
                try:
                    err_json = res.json()
                    detail = err_json.get("error", {}).get("message", detail)
                except:
                    pass
                if res.status_code in (400, 401, 403) or "invalid" in detail.lower():
                    raise ApiKeyAuthError(f"OpenAI API verification failed: {detail}")
                raise ApiKeyNetworkError(f"OpenAI API server error ({res.status_code}): {detail}")
    except httpx.RequestError as e:
        raise ApiKeyNetworkError(f"Could not connect to OpenAI API: {str(e)}")

async def verify_anthropic(api_key: str) -> List[str]:
    url = "https://api.anthropic.com/v1/models"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                models = [m["id"] for m in data.get("data", [])]
                return models
            else:
                detail = "Invalid key"
                try:
                    err_json = res.json()
                    detail = err_json.get("error", {}).get("message", detail)
                except:
                    pass
                if res.status_code in (400, 401, 403) or "invalid" in detail.lower():
                    raise ApiKeyAuthError(f"Anthropic API verification failed: {detail}")
                raise ApiKeyNetworkError(f"Anthropic API server error ({res.status_code}): {detail}")
    except httpx.RequestError as e:
        raise ApiKeyNetworkError(f"Could not connect to Anthropic API: {str(e)}")

async def verify_deepseek(api_key: str) -> List[str]:
    url = "https://api.deepseek.com/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                models = [m["id"] for m in data.get("data", [])]
                return models
            else:
                detail = "Invalid key"
                try:
                    err_json = res.json()
                    detail = err_json.get("error", {}).get("message", detail)
                except:
                    pass
                if res.status_code in (400, 401, 403) or "invalid" in detail.lower():
                    raise ApiKeyAuthError(f"DeepSeek API verification failed: {detail}")
                raise ApiKeyNetworkError(f"DeepSeek API server error ({res.status_code}): {detail}")
    except httpx.RequestError as e:
        raise ApiKeyNetworkError(f"Could not connect to DeepSeek API: {str(e)}")

async def verify_groq(api_key: str) -> List[str]:
    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                models = [
                    m["id"] for m in data.get("data", [])
                    if not any(x in m["id"].lower() for x in ["embed", "whisper"])
                ]
                return models
            else:
                detail = "Invalid key"
                try:
                    err_json = res.json()
                    detail = err_json.get("error", {}).get("message", detail)
                except:
                    pass
                if res.status_code in (400, 401, 403) or "invalid" in detail.lower():
                    raise ApiKeyAuthError(f"Groq API verification failed: {detail}")
                raise ApiKeyNetworkError(f"Groq API server error ({res.status_code}): {detail}")
    except httpx.RequestError as e:
        raise ApiKeyNetworkError(f"Could not connect to Groq API: {str(e)}")

async def verify_openrouter(api_key: str) -> List[str]:
    auth_url = "https://openrouter.ai/api/v1/auth/key"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(auth_url, headers=headers)
            if res.status_code != 200:
                detail = "Invalid key"
                try:
                    err_json = res.json()
                    detail = err_json.get("error", {}).get("message", detail)
                except:
                    pass
                if res.status_code in (400, 401, 403) or "invalid" in detail.lower():
                    raise ApiKeyAuthError(f"OpenRouter API verification failed: {detail}")
                raise ApiKeyNetworkError(f"OpenRouter API server error ({res.status_code}): {detail}")
            
            models_res = await client.get("https://openrouter.ai/api/v1/models")
            if models_res.status_code == 200:
                data = models_res.json()
                models = [m["id"] for m in data.get("data", [])]
                return models
            else:
                raise ApiKeyNetworkError("Failed to fetch OpenRouter models list")
    except httpx.RequestError as e:
        raise ApiKeyNetworkError(f"Could not connect to OpenRouter API: {str(e)}")

async def verify_glm(api_key: str) -> List[str]:
    url = "https://open.bigmodel.cn/api/paas/v4/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                models = [m["id"] for m in data.get("data", [])]
                return models
            else:
                detail = "Invalid key"
                try:
                    err_json = res.json()
                    detail = err_json.get("error", {}).get("message", detail)
                except:
                    pass
                if res.status_code in (400, 401, 403) or "invalid" in detail.lower():
                    raise ApiKeyAuthError(f"GLM API verification failed: {detail}")
                raise ApiKeyNetworkError(f"GLM API server error ({res.status_code}): {detail}")
    except httpx.RequestError as e:
        raise ApiKeyNetworkError(f"Could not connect to GLM API: {str(e)}")

async def verify_alibaba(api_key: str) -> List[str]:
    url = "https://dashscope.aliyuncs.com/api/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                models = []
                data_obj = data.get("data", {})
                if isinstance(data_obj, dict):
                    models_list = data_obj.get("models", [])
                    for m in models_list:
                        name = m.get("model_name")
                        if name:
                            models.append(name)
                if not models:
                    models = [m["id"] for m in data.get("data", []) if "id" in m]
                return models
            else:
                detail = "Invalid key"
                try:
                    err_json = res.json()
                    detail = err_json.get("error", {}).get("message", detail)
                except:
                    pass
                if res.status_code in (400, 401, 403) or "invalid" in detail.lower():
                    raise ApiKeyAuthError(f"Alibaba API verification failed: {detail}")
                raise ApiKeyNetworkError(f"Alibaba API server error ({res.status_code}): {detail}")
    except httpx.RequestError as e:
        raise ApiKeyNetworkError(f"Could not connect to Alibaba API: {str(e)}")

# ─── Search Provider Verification ─────────────────────────────────────────────

async def verify_tavily(api_key: str) -> List[str]:
    """Verify Tavily API key by running a minimal test search."""
    url = "https://api.tavily.com/search"
    payload = {"api_key": api_key, "query": "test", "max_results": 1, "search_depth": "basic"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                return ["tavily-search"]
            detail = "Invalid key"
            try:
                err_json = res.json()
                detail = err_json.get("detail") or err_json.get("message") or err_json.get("error", {}).get("message", detail)
            except:
                pass
            if res.status_code in (400, 401, 403) or "invalid" in detail.lower():
                raise ApiKeyAuthError(f"Tavily verification failed ({res.status_code}): {detail}")
            raise ApiKeyNetworkError(f"Tavily API server error ({res.status_code}): {detail}")
    except httpx.RequestError as e:
        raise ApiKeyNetworkError(f"Could not connect to Tavily API: {str(e)}")

async def verify_serpapi(api_key: str) -> List[str]:
    """Verify SerpAPI key via the account endpoint."""
    url = f"https://serpapi.com/account?api_key={api_key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                if data.get("account_id") or data.get("email"):
                    return ["google-search", "bing-search", "youtube-search"]
            detail = "Invalid key"
            try:
                err_json = res.json()
                detail = err_json.get("error") or err_json.get("message", detail)
            except:
                pass
            if res.status_code in (400, 401, 403) or "invalid" in detail.lower():
                raise ApiKeyAuthError(f"SerpAPI verification failed ({res.status_code}): {detail}")
            raise ApiKeyNetworkError(f"SerpAPI server error ({res.status_code}): {detail}")
    except httpx.RequestError as e:
        raise ApiKeyNetworkError(f"Could not connect to SerpAPI: {str(e)}")

async def verify_exa(api_key: str) -> List[str]:
    """Verify Exa AI key by running a minimal test search."""
    url = "https://api.exa.ai/search"
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    payload = {"query": "test", "numResults": 1}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code in (200, 201):
                return ["exa-search", "exa-find-similar"]
            detail = "Invalid key"
            try:
                err_json = res.json()
                detail = err_json.get("error") or err_json.get("message", detail)
            except:
                pass
            if res.status_code in (400, 401, 403) or "invalid" in detail.lower():
                raise ApiKeyAuthError(f"Exa AI verification failed ({res.status_code}): {detail}")
            raise ApiKeyNetworkError(f"Exa AI server error ({res.status_code}): {detail}")
    except httpx.RequestError as e:
        raise ApiKeyNetworkError(f"Could not connect to Exa AI API: {str(e)}")

async def verify_provider_api_key_and_fetch_models(provider_name: str, api_key: str) -> List[str]:
    provider = provider_name.lower().strip()
    if provider in ["google", "gemini"]:
        return await verify_google(api_key)
    elif provider == "openai":
        return await verify_openai(api_key)
    elif provider == "anthropic":
        return await verify_anthropic(api_key)
    elif provider == "deepseek":
        return await verify_deepseek(api_key)
    elif provider == "groq":
        return await verify_groq(api_key)
    elif provider == "openrouter":
        return await verify_openrouter(api_key)
    elif provider == "glm":
        return await verify_glm(api_key)
    elif provider == "alibaba":
        return await verify_alibaba(api_key)
    elif provider == "tavily":
        return await verify_tavily(api_key)
    elif provider == "serpapi":
        return await verify_serpapi(api_key)
    elif provider == "exa":
        return await verify_exa(api_key)
    else:
        raise Exception(f"Unsupported provider: {provider_name}")


# ─── API Routes ────────────────────────────────────────────────────────────────────

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
        if not k.encrypted_api_key:
            continue
        try:
            raw_key = decrypt_api_key(k.encrypted_api_key)
        except Exception:
            raw_key = k.encrypted_api_key

        masked_key = ""
        if len(raw_key) > 8:
            masked_key = f"{raw_key[:4]}...{raw_key[-4:]}"
        else:
            masked_key = "****"

        provider_name = k.provider_name.lower().strip()
        if provider_name == "gemini":
            provider_name = "google"
        out_keys.append(ApiKeyOut(
            provider_name=provider_name,
            masked_key=masked_key,
            is_verified=(k.status == "VERIFIED"),
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
    if provider_name == "gemini":
        provider_name = "google"

    supported = ["google", "groq", "openrouter", "openai", "anthropic", "deepseek", "alibaba", "glm",
                 "tavily", "serpapi", "exa"]
    if provider_name not in supported:
        raise HTTPException(status_code=400, detail="Unsupported provider name.")

    # Encrypt key
    encrypted_val = encrypt_api_key(schema.api_key)
    now = datetime.now(timezone.utc)

    # Check if existing key (handle both 'google' and legacy 'gemini' names)
    search_providers = [provider_name]
    if provider_name == "google":
        search_providers.append("gemini")

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.user_id == current_user.id,
            ApiKey.provider_name.in_(search_providers)
        )
    )
    existing_key = result.scalars().first()
    if existing_key and existing_key.provider_name == "gemini":
        existing_key.provider_name = "google"

    db_key = existing_key
    if not db_key:
        db_key = ApiKey(
            user_id=current_user.id,
            provider_name=provider_name,
        )
        db.add(db_key)

    # Update to verifying state
    db_key.encrypted_api_key = encrypted_val
    db_key.status = "VERIFYING"
    db_key.last_checked = now
    db_key.last_error = None
    db_key.available_models = []
    await db.commit()
    await db.refresh(db_key)

    # Perform live verification and models fetch
    try:
        models = await verify_provider_api_key_and_fetch_models(provider_name, schema.api_key)
        now = datetime.now(timezone.utc)
        db_key.status = "VERIFIED"
        db_key.verified_at = now
        db_key.last_checked = now
        db_key.available_models = models if isinstance(models, list) else []
        db_key.last_error = None
    except Exception as e:
        now = datetime.now(timezone.utc)
        db_key.status = "INVALID"
        db_key.last_error = str(e)[:900]  # truncate to column limit
        db_key.available_models = []
        db_key.last_checked = now
        await db.commit()
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    await db.refresh(db_key)

    raw_key = schema.api_key
    masked_key = f"{raw_key[:4]}...{raw_key[-4:]}" if len(raw_key) > 8 else "****"

    return ApiKeyOut(
        provider_name=db_key.provider_name,
        masked_key=masked_key,
        is_verified=True,
        created_at=db_key.created_at
    )


@router.delete("/{provider_name}")
async def delete_api_key(
    provider_name: str,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    provider_name = provider_name.lower().strip()
    if provider_name == "gemini":
        provider_name = "google"

    search_providers = [provider_name]
    if provider_name == "google":
        search_providers.append("gemini")

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.user_id == current_user.id,
            ApiKey.provider_name.in_(search_providers)
        )
    )
    existing_key = result.scalars().first()
    if not existing_key:
        raise HTTPException(status_code=404, detail="API key not found.")

    await db.delete(existing_key)
    await db.commit()
    return {"detail": f"API key for {provider_name} successfully deleted."}


# ─── Providers List & Refresh endpoints ────────────────────────────────────────────

@providers_router.get("", response_model=List[ProviderOut])
async def list_providers(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id)
    )
    db_keys = result.scalars().all()
    keys_map = {}
    for k in db_keys:
        name = k.provider_name.lower().strip()
        if name == "gemini":
            name = "google"
        keys_map[name] = k
    
    supported_providers = ["google", "openai", "anthropic", "deepseek", "groq", "openrouter", "glm", "alibaba",
                           "tavily", "serpapi", "exa"]
    out = []
    for pid in supported_providers:
        db_record = keys_map.get(pid)
        if db_record:
            status_str = db_record.status
            saved = bool(db_record.encrypted_api_key)
            verified = (status_str == "VERIFIED")
            enabled = (status_str == "VERIFIED")
            last_checked = db_record.last_checked
            available_models = db_record.available_models or []
            last_error = db_record.last_error
        else:
            status_str = "UNCONFIGURED"
            saved = False
            verified = False
            enabled = False
            last_checked = None
            available_models = []
            last_error = None
            
        out.append(ProviderOut(
            id=pid,
            status=status_str,
            saved=saved,
            verified=verified,
            enabled=enabled,
            lastChecked=last_checked,
            availableModels=available_models,
            lastError=last_error
        ))
    return out


@providers_router.post("/refresh", response_model=List[ProviderOut])
async def refresh_providers(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id)
    )
    db_keys = result.scalars().all()
    
    for k in db_keys:
        if k.encrypted_api_key:
            prev_status = k.status
            prev_models = k.available_models
            k.status = "VERIFYING"
            await db.commit()
            try:
                raw_key = decrypt_api_key(k.encrypted_api_key)
                models = await verify_provider_api_key_and_fetch_models(k.provider_name, raw_key)
                now = datetime.now(timezone.utc)
                k.status = "VERIFIED"
                k.verified_at = now
                k.last_checked = now
                k.available_models = models if isinstance(models, list) else []
                k.last_error = None
            except ApiKeyAuthError as e:
                now = datetime.now(timezone.utc)
                k.status = "INVALID"
                k.last_error = str(e)[:900]
                k.available_models = []
                k.last_checked = now
            except Exception as e:
                now = datetime.now(timezone.utc)
                # Network or transient server error: preserve prior status & models
                k.status = prev_status if prev_status in ("VERIFIED", "INVALID") else "VERIFIED"
                k.available_models = prev_models or []
                k.last_error = f"Transient check warning: {str(e)[:800]}"
                k.last_checked = now
            db.add(k)
    await db.commit()
    return await list_providers(current_user=current_user, db=db)
