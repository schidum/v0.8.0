from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
import uvicorn
from pathlib import Path

from app.database import init_db, AsyncSessionLocal
from app.routers import api_router
from app.repositories import PersonRepository
from app.services import AuthService
from app.models import Person, PersonRole, RoleEnum

app = FastAPI(
    title="Агро API — Точное земледелие",
    version="0.8.0",
    description=" веб API и мобильный API CQRS, Celery, RabbitMQ , Ownership, WebSocket"
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-App-Client"],
)

app.include_router(api_router)

@app.on_event("startup")
async def create_default_superuser():
    async with AsyncSessionLocal() as db:
        repo = PersonRepository(db)
        admin = await repo.get_by_login("admin")
        if not admin:
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
            print("Суперюзер admin/admin создан")

@app.get("/")
async def root():
    return {"message": "Агро API v0.8.0", "admin": "/admin", "docs": "/docs"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info")