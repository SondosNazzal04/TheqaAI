from fastapi import FastAPI
from app.core.settings import settings
from app.core.middleware import setup_middlewares
from app.core.errors import setup_exception_handlers

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

setup_middlewares(app)
setup_exception_handlers(app)

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME}
