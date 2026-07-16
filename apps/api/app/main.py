from fastapi import FastAPI
from app.core.settings import settings
from app.core.middleware import setup_middlewares
from app.core.errors import setup_exception_handlers
from app.api.v1.routes import auth, trust, deals, webhooks

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

setup_middlewares(app)
setup_exception_handlers(app)

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}", tags=["user"]) # for /me endpoint
app.include_router(trust.router, prefix=f"{settings.API_V1_STR}/trust", tags=["trust"])
app.include_router(deals.router, prefix=f"{settings.API_V1_STR}/deals", tags=["deals"])
app.include_router(webhooks.router, prefix=f"{settings.API_V1_STR}/webhooks", tags=["webhooks"])

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME}
