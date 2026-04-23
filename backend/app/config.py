"""
配置管理模块
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""

    # 数据库配置
    database_url: str = "postgresql://laserclaw:laserclaw123@db:5432/laserclaw"

    # 文件上传配置
    upload_dir: str = "/app/uploads"
    max_upload_size: int = 10485760  # 10MB

    # AI提供者配置
    ai_provider: str = "mock"  # mock, openai, anthropic

    # CORS配置
    cors_origins: list = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
