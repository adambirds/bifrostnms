from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tortoise import Tortoise

from bifrostnms.api.auth import router as auth_router
from bifrostnms.api.security import router as security_router
from bifrostnms.api.two_factor import router as two_factor_router
from bifrostnms.api.webauthn import router as webauthn_router
from bifrostnms.auth.redis import close_redis, get_redis
from bifrostnms.config import get_settings
from bifrostnms.database import TORTOISE_ORM

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await Tortoise.init(config=TORTOISE_ORM)
    if settings.auto_create_schema:
        await Tortoise.generate_schemas(safe=True)
    await get_redis().ping()
    yield
    await close_redis()
    await Tortoise.close_connections()


app = FastAPI(title="BifrostNMS", version="0.1.0-dev", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(two_factor_router, prefix="/api/v1")
app.include_router(webauthn_router, prefix="/api/v1")
app.include_router(security_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
