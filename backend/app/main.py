"""
FastAPI主应用
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .config import get_settings
from .database import engine, Base
from .api import cases, attachments, generation
import os

settings = get_settings()

# 创建数据库表
Base.metadata.create_all(bind=engine)

# 创建上传目录
os.makedirs(settings.upload_dir, exist_ok=True)

# 创建FastAPI应用
app = FastAPI(
    title="LaserClaw API",
    description="激光实验辅助系统API",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件（上传的附件）
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# 注册路由
app.include_router(cases.router, prefix="/api/cases", tags=["cases"])
app.include_router(attachments.router, prefix="/api", tags=["attachments"])
app.include_router(generation.router, prefix="/api/cases", tags=["generation"])


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "LaserClaw API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}
