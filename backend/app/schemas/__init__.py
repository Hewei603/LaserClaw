"""
Pydantic模式定义
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime


# 实验案例模式
class ExperimentCaseBase(BaseModel):
    """实验案例基础模式"""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    cavity_type: str = Field(..., pattern="^(linear|ring|bow-tie|custom)$")
    goal: str = Field(..., min_length=1)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    symptoms: List[str] = Field(default_factory=list)


class ExperimentCaseCreate(ExperimentCaseBase):
    """创建实验案例请求模式"""
    pass


class ExperimentCaseUpdate(BaseModel):
    """更新实验案例请求模式"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    cavity_type: Optional[str] = Field(None, pattern="^(linear|ring|bow-tie|custom)$")
    goal: Optional[str] = Field(None, min_length=1)
    parameters: Optional[Dict[str, Any]] = None
    symptoms: Optional[List[str]] = None


class ExperimentCaseResponse(ExperimentCaseBase):
    """实验案例响应模式"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 附件模式
class AttachmentResponse(BaseModel):
    """附件响应模式"""
    id: int
    case_id: int
    filename: str
    file_type: Optional[str] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


# 生成内容模式
class GeneratedContentResponse(BaseModel):
    """生成内容响应模式"""
    id: int
    case_id: int
    content_type: str
    content: Dict[str, Any]
    generated_at: datetime

    class Config:
        from_attributes = True


# 生成请求模式
class GenerateRequest(BaseModel):
    """生成内容请求模式"""
    pass  # 可以扩展添加额外参数
