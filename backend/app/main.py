import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app import models  # register ORM mappings
from app.core.config import settings
from app.core.database import get_db
from app.routes.patient_routes import router as patient_router
from app.routes.auth_routes import router as auth_router
from app.routes.admin_routes import router as admin_router
from app.routes.assistant_routes import router as assistant_router
from app.routes.billing_routes import router as billing_router
from app.routes.clinical_routes import router as clinical_router
from app.routes.provider_routes import router as provider_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    description="Patient portal, voice assistant, and billing API",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(patient_router, prefix=settings.api_v1_prefix)
app.include_router(assistant_router, prefix=settings.api_v1_prefix)
app.include_router(clinical_router, prefix=settings.api_v1_prefix)
app.include_router(provider_router, prefix=settings.api_v1_prefix)
app.include_router(billing_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)

@app.get("/", tags=["System"])
def home():
    return {"message": f"{settings.app_name} backend is running"}


@app.get(f"{settings.api_v1_prefix}/health/live", tags=["System"])
def liveness():
    return {"status": "alive", "service": "backend"}


@app.get(f"{settings.api_v1_prefix}/health", tags=["System"])
@app.get(f"{settings.api_v1_prefix}/health/ready", tags=["System"])
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable", "service": "backend"})
    return {"status": "healthy", "service": "backend"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled application exception", exc_info=(type(exc), exc, exc.__traceback__))
    origin = request.headers.get("origin")
    headers = {}
    if origin and origin in settings.cors_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Idempotency-Key"
        headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred."}, headers=headers)
