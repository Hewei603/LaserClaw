"""Experiment case API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..knowledge.ingestion import upsert_case_source
from ..models import ExperimentCase
from ..observability.audit import record_audit
from ..schemas import ExperimentCaseCreate, ExperimentCaseResponse, ExperimentCaseUpdate

router = APIRouter()


def get_case_or_404(case_id: int, db: Session) -> ExperimentCase:
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} does not exist")
    return case


@router.post("", response_model=ExperimentCaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(case_data: ExperimentCaseCreate, db: Session = Depends(get_db)):
    """Create an experiment case and index it for retrieval."""
    case = ExperimentCase(**case_data.model_dump())
    db.add(case)
    db.flush()
    upsert_case_source(db, case)
    record_audit(db, action="case.create", resource_type="case", resource_id=str(case.id))
    db.commit()
    db.refresh(case)
    return case


@router.get("", response_model=list[ExperimentCaseResponse])
async def list_cases(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List experiment cases."""
    return db.query(ExperimentCase).offset(skip).limit(limit).all()


@router.get("/{case_id}", response_model=ExperimentCaseResponse)
async def get_case(case_id: int, db: Session = Depends(get_db)):
    """Get one experiment case."""
    return get_case_or_404(case_id, db)


@router.put("/{case_id}", response_model=ExperimentCaseResponse)
async def update_case(case_id: int, case_data: ExperimentCaseUpdate, db: Session = Depends(get_db)):
    """Update an experiment case and refresh the knowledge index."""
    case = get_case_or_404(case_id, db)
    for field, value in case_data.model_dump(exclude_unset=True).items():
        setattr(case, field, value)
    upsert_case_source(db, case)
    record_audit(db, action="case.update", resource_type="case", resource_id=str(case.id))
    db.commit()
    db.refresh(case)
    return case


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(case_id: int, db: Session = Depends(get_db)):
    """Delete an experiment case."""
    case = get_case_or_404(case_id, db)
    record_audit(db, action="case.delete", resource_type="case", resource_id=str(case.id))
    db.delete(case)
    db.commit()
    return None
