import asyncio
import json
import logging
import sys
from pathlib import Path

# Add backend root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import AsyncSessionLocal, init_db
from app.routers.secondary_services import enable_secondary_service, EnableSecondaryRequest, _ensure_secondary_table
from app.models.secondary_service import SecondaryService
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("enable_all")

async def main():
    log.info("Initializing database...")
    await init_db()
    
    async with AsyncSessionLocal() as db:
        log.info("Ensuring secondary services are populated in DB...")
        await _ensure_secondary_table(db)
        
        # Unique port assignments to avoid conflicts with host listeners (Apache/etc)
        configs = {
            "portainer": {
                "port": 9443, 
                "password": "SecurePortainerAdminPass123!"
            },
            "minio": {
                "port_api": 9000, 
                "port_console": 9001, 
                "root_user": "minioadmin", 
                "root_password": "SecureMinioPassword123!"
            },
            "n8n": {
                "port": 5678, 
                "encryption_key": "SecureN8NEncryptionKey123!", 
                "timezone": "UTC"
            },
            "uptime_kuma": {
                "port": 3004  # Avoid host Apache on 3001
            },
            "netdata": {
                "port": 19999
            },
            "changedetection": {
                "port": 5000
            },
            "vaultwarden": {
                "port": 8082,  # Avoid host Apache on 8081
                "admin_token": "SecureVaultwardenToken123!"
            },
            "nginx_proxy_manager": {
                "port_http": 8080, 
                "port_https": 8443, 
                "port_admin": 8181
            },
            "mediamtx": {
                "rtsp_port": 8554, 
                "rtmp_port": 1935, 
                "hls_port": 8888, 
                "webrtc_port": 8889, 
                "webrtc_udp_port": 8189, 
                "srt_port": 8890
            },
            "mediadump": {
                "port": 5001
            }
        }
        
        for key, cfg in configs.items():
            log.info("----------------------------------------")
            log.info(f"Processing service: {key}")
            
            # Check current DB status
            existing = (await db.execute(select(SecondaryService).where(SecondaryService.key == key))).scalar_one_or_none()
            if existing and existing.enabled:
                log.info(f"Service {key} is already marked as enabled in DB. Re-deploying to ensure health...")
                # To re-deploy, we temporarily disable it to clear any old state/containers
                from app.routers.secondary_services import disable_secondary_service
                try:
                    await disable_secondary_service(key=key, db=db, _=None)
                except Exception as e:
                    log.warning(f"Disable step during redeployment of {key} warned/failed: {e}")
            
            try:
                log.info(f"Enabling service {key} with config: {cfg}")
                req = EnableSecondaryRequest(config=cfg)
                res = await enable_secondary_service(key=key, body=req, db=db, _=None)
                log.info(f"Successfully enabled {key}: {res}")
            except Exception as e:
                log.error(f"Failed to enable {key}: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
