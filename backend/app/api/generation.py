"""
内容生成API路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import ExperimentCase, GeneratedContent
from ..schemas import GeneratedContentResponse, GenerateRequest
from ..providers import get_ai_provider

router = APIRouter()


@router.post("/{case_id}/generate-plan", response_model=GeneratedContentResponse)
async def generate_plan(
    case_id: int,
    request: GenerateRequest = GenerateRequest(),
    db: Session = Depends(get_db)
):
    """生成实验计划"""
    # 获取案例
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"案例 {case_id} 不存在"
        )

    # 准备案例数据
    case_data = {
        "title": case.title,
        "description": case.description,
        "cavity_type": case.cavity_type,
        "goal": case.goal,
        "parameters": case.parameters,
        "symptoms": case.symptoms
    }

    # 生成计划
    provider = get_ai_provider()
    content = await provider.generate_plan(case_data)

    # 保存生成的内容
    generated = GeneratedContent(
        case_id=case_id,
        content_type="plan",
        content=content
    )
    db.add(generated)
    db.commit()
    db.refresh(generated)

    return generated


@router.post("/{case_id}/generate-rezonator", response_model=GeneratedContentResponse)
async def generate_rezonator(
    case_id: int,
    request: GenerateRequest = GenerateRequest(),
    db: Session = Depends(get_db)
):
    """生成ReZonator模式草稿"""
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"案例 {case_id} 不存在"
        )

    case_data = {
        "title": case.title,
        "cavity_type": case.cavity_type,
        "parameters": case.parameters
    }

    provider = get_ai_provider()
    content = await provider.generate_rezonator_schema(case_data)

    generated = GeneratedContent(
        case_id=case_id,
        content_type="rezonator",
        content=content
    )
    db.add(generated)
    db.commit()
    db.refresh(generated)

    return generated


@router.post("/{case_id}/generate-troubleshooting", response_model=GeneratedContentResponse)
async def generate_troubleshooting(
    case_id: int,
    request: GenerateRequest = GenerateRequest(),
    db: Session = Depends(get_db)
):
    """生成故障排查建议"""
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"案例 {case_id} 不存在"
        )

    case_data = {
        "title": case.title,
        "cavity_type": case.cavity_type,
        "parameters": case.parameters
    }

    provider = get_ai_provider()
    content = await provider.generate_troubleshooting(case.symptoms, case_data)

    generated = GeneratedContent(
        case_id=case_id,
        content_type="troubleshooting",
        content=content
    )
    db.add(generated)
    db.commit()
    db.refresh(generated)

    return generated


@router.post("/{case_id}/generate-report", response_model=GeneratedContentResponse)
async def generate_report(
    case_id: int,
    request: GenerateRequest = GenerateRequest(),
    db: Session = Depends(get_db)
):
    """生成实验报告"""
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"案例 {case_id} 不存在"
        )

    case_data = {
        "title": case.title,
        "description": case.description,
        "cavity_type": case.cavity_type,
        "goal": case.goal,
        "parameters": case.parameters,
        "symptoms": case.symptoms
    }

    provider = get_ai_provider()
    content = await provider.generate_report(case_data)

    generated = GeneratedContent(
        case_id=case_id,
        content_type="report",
        content=content
    )
    db.add(generated)
    db.commit()
    db.refresh(generated)

    return generated


@router.get("/{case_id}/generated-contents", response_model=list[GeneratedContentResponse])
async def list_generated_contents(
    case_id: int,
    content_type: str = None,
    db: Session = Depends(get_db)
):
    """获取案例的生成内容列表"""
    query = db.query(GeneratedContent).filter(GeneratedContent.case_id == case_id)

    if content_type:
        query = query.filter(GeneratedContent.content_type == content_type)

    contents = query.order_by(GeneratedContent.generated_at.desc()).all()
    return contents
