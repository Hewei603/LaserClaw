"""
生成内容模型
"""
from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class GeneratedContent(Base):
    """生成内容表"""

    __tablename__ = "generated_contents"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("experiment_cases.id"), nullable=False)
    content_type = Column(String(50), nullable=False)  # plan, rezonator, troubleshooting, report
    content = Column(JSON, nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    case = relationship("ExperimentCase", back_populates="generated_contents")
