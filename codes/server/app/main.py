"""FastAPI 入口。

浏览器打开 /docs 可以点着测所有接口。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(f"{settings.api_prefix}/health", tags=["其他"])
def health() -> dict:
    """存活探针，给 Nginx / 监控用。"""
    return {"status": "ok", "app": settings.app_name}


# ── 路由挂载（Phase 1 起逐个加）──────────────────────
from app.routers import admin, auth  # noqa: E402

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)

# 后续：classes / students / lessons / approvals / exports
