import asyncio
import logging
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.user import ApiKey
from app.core.security import decrypt_api_key
from app.api.api_keys import verify_provider_api_key_and_fetch_models, ApiKeyAuthError
from sqlalchemy.sql import func

logger = logging.getLogger("app.workers.health_check")

async def provider_health_check_loop():
    logger.info("Starting background provider health check loop")
    # Wait a few seconds for database initialization on startup
    await asyncio.sleep(5)
    while True:
        try:
            logger.info("Running provider health checks...")
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(ApiKey))
                keys = result.scalars().all()
                
                for k in keys:
                    if not k.encrypted_api_key:
                        continue
                    try:
                        raw_key = decrypt_api_key(k.encrypted_api_key)
                        models = await verify_provider_api_key_and_fetch_models(k.provider_name, raw_key)
                        k.status = "VERIFIED"
                        k.verified_at = func.now()
                        k.last_checked = func.now()
                        k.available_models = models
                        k.last_error = None
                    except ApiKeyAuthError as e:
                        logger.warning(f"Health check found invalid key for provider {k.provider_name} (key ID {k.id}): {e}")
                        k.status = "INVALID"
                        k.last_error = str(e)[:900]
                        k.available_models = []
                        k.last_checked = func.now()
                    except Exception as e:
                        logger.warning(f"Transient health check issue for provider {k.provider_name} (key ID {k.id}): {e}")
                        k.last_error = f"Transient warning: {str(e)[:800]}"
                        k.last_checked = func.now()
                        # Crucial: DO NOT change status to INVALID and DO NOT clear available_models if key was previously valid
                        if k.status != "INVALID" and not k.status:
                            k.status = "VERIFIED"
                    db.add(k)
                await db.commit()
            logger.info("Provider health checks completed.")
        except Exception as e:
            logger.error(f"Error in provider health check loop: {e}")
        
        # Sleep for 6 hours (6 * 3600 seconds)
        await asyncio.sleep(21600)
