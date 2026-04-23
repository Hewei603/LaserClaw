"""
实验案例API路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models import ExperimentCase
from ..schemas import (
    ExperimentCaseCreate,
    ExperimentCaseUpdate,
    ExperimentCaseResponse
)

router = APIRouter()


@router.post("", response_model=ExperimentCaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    case_data: ExperimentCaseCreate,
    db: Session = Depends(get_db)
):
    """创建实验案例"""
    case = ExperimentCase(**case_data.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get("", response_model=List[ExperimentCaseResponse])
async def list_cases(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取实验案例列表"""
    cases = db.query(ExperimentCase).offset(skip).limit(limit).all()
    return cases


@router.get("/{case_id}", response_model=ExperimentCaseResponse)
async def get_case(
    case_id: int,
    db: Session = Depends(get_db)
):
    """获取单个实验案例"""
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"案例 {case_id} 不存在"
        )
    return case


@router.put("/{case_id}", response_model=ExperimentCaseResponse)
async def update_case(
    case_id: int,
    case_data: ExperimentCaseUpdate,
    db: Session = Depends(get_db)
):
    """更新实验案例"""
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"案例 {case_id} 不存在"
        )

    # 更新字段
    update_data = case_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(case, field, value)

    db.commit()
    db.refresh(case)
    return case


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(
    case_id: int,
    db: Session = Depends(get_db)
):
    """删除实验案例"""
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"案例 {case_id} 不存在"
        )

    db.delete(case)
    db.commit()
    return None
