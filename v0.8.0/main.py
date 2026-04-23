from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
import uvicorn
import logging
from pathlib import Path

from app.config import settings
from app.database import init_db, AsyncSessionLocal
from app.routers import api_router
from app.repositories import PersonRepository
from app.services import AuthService
from app.models import Person, PersonRole, RoleEnum

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description="веб API и мобильный API CQRS, Celery, RabbitMQ, Ownership, WebSocket"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# @app.middleware("http")
# async def add_security_headers(request, call_next):
#     response = await call_next(request)

#     # Основные защитные заголовки
#     response.headers["X-Content-Type-Options"] = "nosniff"
#     response.headers["X-Frame-Options"] = "DENY"
#     response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
#     response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
#     response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

#     # === ИСПРАВЛЕННЫЙ CSP ===
#     response.headers["Content-Security-Policy"] = (
#         "default-src 'self'; "
#         "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com "
#                 "https://cdn.jsdelivr.net https://unpkg.com; "   # ← добавил для Swagger + Leaflet
#         "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com "
#                 "https://cdn.jsdelivr.net https://unpkg.com; "
#         "font-src 'self' https://cdnjs.cloudflare.com; "
#         "img-src 'self' data: https://cdn.jsdelivr.net https://unpkg.com; "
#         "connect-src 'self' ws://127.0.0.1:* ws://localhost:* http://127.0.0.1:* http://localhost:*;"
#     )

#     return response

@app.get("/admin", response_class=FileResponse)
async def admin_page():
    return FileResponse("admin.html")

@app.get("/admin.html", response_class=FileResponse)
async def admin_page_html():
    return FileResponse("admin.html")


# ==================== CORS CONFIGURATION ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
    max_age=settings.CORS_MAX_AGE,
)

logger.info(f"CORS configured for environment: {settings.ENVIRONMENT}")
logger.info(f"Allowed origins: {settings.cors_origins_list}")

app.include_router(api_router)

@app.on_event("startup")
async def create_default_superuser():
    """Create default admin user on startup if not exists."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        async with AsyncSessionLocal() as db:
            repo = PersonRepository(db)
            try:
                admin = await repo.get_by_login("admin")
            except Exception as e:
                logger.error(f"Error checking for existing admin user: {e}")
                return
            
            if not admin:
                try:
                    admin_user = Person(
                        full_name="Супер Администратор",
                        login="admin",
                        password_hash=AuthService.hash_password("admin"),
                        is_active=True,
                    )
                    admin_user.roles.extend([
                        PersonRole(role=RoleEnum.manager),
                        PersonRole(role=RoleEnum.chemist),
                        PersonRole(role=RoleEnum.agronomist)
                    ])
                    await repo.create(admin_user)
                    logger.info("Default admin user created successfully (admin/admin)")
                except Exception as e:
                    logger.error(f"Failed to create default admin user: {e}")
            else:
                logger.info("Admin user already exists")
    except Exception as e:
        logger.error(f"Critical error in startup admin creation: {e}")

@app.get("/")
async def root():
    return {"message": "Агро API v0.8.0", "admin": "/admin", "docs": "/docs"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info")