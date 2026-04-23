"""
附件模型
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Attachment(Base):
    """附件表"""

    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("experiment_cases.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(512), nullable=False)
    file_type = Column(String(50))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    case = relationship("ExperimentCase", back_populates="attachments")
