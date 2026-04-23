"""
实验案例模型
"""
from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class ExperimentCase(Base):
    """实验案例表"""

    __tablename__ = "experiment_cases"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    cavity_type = Column(String(50), nullable=False)  # linear, ring, bow-tie, custom
    goal = Column(Text, nullable=False)
    parameters = Column(JSON, default={})  # 键值对参数
    symptoms = Column(JSON, default=[])  # 症状列表
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关系
    attachments = relationship("Attachment", back_populates="case", cascade="all, delete-orphan")
    generated_contents = relationship("GeneratedContent", back_populates="case", cascade="all, delete-orphan")
