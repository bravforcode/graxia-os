import sys
import os
import time
from typing import Callable, Optional, List, Any, Dict
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings

# Ensure shared packages are importable if running from service context
# In production, these should be installed as packages
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from packages.logging.python.logger import get_logger, set_context
from packages.auth.python.jwt_auth import decode_access_token

logger = get_logger("bravos_core")

class ApiError(Exception):
    def __init__(self, status_code: int, message: str, details: Optional[Any] = None):
        self.status_code = status_code
        self.message = message
        self.details = details

class CoreSettings(BaseSettings):
    JWT_SECRET: str = os.getenv("JWT_SECRET", "bravos_fallback_secret_key_change_me_in_prod")
    SERVICE_NAME: str = "unnamed_service"

def create_app(title: str, version: str = "1.0.0", settings: Optional[CoreSettings] = None) -> FastAPI:
    app = FastAPI(title=title, version=version)
    
    if settings is None:
        settings = CoreSettings()

    # --- Health Check ---
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "service": settings.SERVICE_NAME,
            "timestamp": time.time()
        }

    # --- Exception Handling ---
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.message,
                    "details": exc.details,
                    "code": exc.status_code
                }
            }
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception: {str(exc)}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "Internal Server Error",
                    "details": str(exc) if os.getenv("DEBUG") else None,
                    "code": 500
                }
            }
        )

    # --- HR-10 & Logging Middleware ---
    @app.middleware("http")
    async def base_middleware(request: Request, call_next: Callable):
        # 1. Setup Request Context for Logger
        trace_id = request.headers.get("X-Trace-ID", f"trace-{time.time()}")
        mission_id = request.headers.get("X-Mission-ID")
        set_context(trace_id=trace_id, mission_id=mission_id)
        
        # 2. Exempt paths from Auth
        if request.url.path in ["/health", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)

        # 3. HR-10 Enforcement
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning(f"HR-10 Violation: Missing auth token on {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "HR-10 Violation: Internal service requests must be authenticated via Identity Broker."}
            )

        try:
            token = auth_header.split(" ")[1]
            payload = decode_access_token(token, settings.JWT_SECRET)
            request.state.user = payload
            # Update mission context if available in token
            if payload.get("mission_id"):
                set_context(trace_id=trace_id, mission_id=payload["mission_id"])
        except Exception as e:
            logger.error(f"HR-10 Violation: Invalid token. {str(e)}")
            return JSONResponse(
                status_code=401,
                content={"detail": f"HR-10 Violation: {str(e)}"}
            )

        # 4. Execute Request
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # 5. Log completion
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code}",
            extra={"process_time": process_time}
        )
        
        return response

    return app
