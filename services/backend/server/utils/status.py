import httpx
from redis.asyncio import Redis
from loguru import logger

from codeflower_db.types import ServiceStatus

from ..core import config
from . import proxmox
        

async def check_redis_status(r: Redis) -> ServiceStatus:
    try:
        if await r.ping():  # type: ignore
            return ServiceStatus.HEALTHY
        logger.warning("Redis ping failed")
        return ServiceStatus.UNHEALTHY
    except Exception as e:
        logger.error(f"Error checking Redis status: {e}")
        return ServiceStatus.NOT_RESPONDING
    

async def check_docker_registry_status() -> ServiceStatus:
    async with httpx.AsyncClient() as client:
        try:
            url = f"http://{config.settings.REGISTRY_URL.rstrip('/')}/v2/"
            response = await client.get(url, timeout=5)
            
            if response.status_code in (200, 401):
                return ServiceStatus.HEALTHY
            else:
                logger.warning(f"Docker Registry returned unexpected status code: {response.status_code}")
                return ServiceStatus.UNHEALTHY
        except Exception as e:
            logger.error(f"Error checking Docker Registry status: {e}")
            return ServiceStatus.NOT_RESPONDING
        
async def check_proxmox_status(proxmox_client: proxmox.Client) -> ServiceStatus:
    try:
        if proxmox_client.test_connection():
            return ServiceStatus.HEALTHY
        else:
            logger.warning("Proxmox test_connection returned False")
            return ServiceStatus.UNHEALTHY
    except Exception as e:
        logger.error(f"Error checking Proxmox status: {e}")
        return ServiceStatus.NOT_RESPONDING