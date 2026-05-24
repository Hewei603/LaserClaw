"""Collaboration API for users, groups, projects, and memberships."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth.security import Principal, get_current_principal
from ..database import get_db
from ..models import Group, GroupMember, Organization, Project, ProjectMember, User
from ..observability.audit import record_audit
from ..schemas import (
    GroupCreate,
    GroupResponse,
    MembershipCreate,
    OrganizationCreate,
    OrganizationResponse,
    ProjectCreate,
    ProjectResponse,
    UserCreate,
    UserResponse,
)

router = APIRouter()
ADMIN_ROLES = {"admin"}


def _require_admin(principal: Principal) -> None:
    if principal.role not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


def _get_or_404(db: Session, model, object_id: int, label: str):
    obj = db.query(model).filter(model.id == object_id).first()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} {object_id} does not exist")
    return obj


@router.post("/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require_admin(principal)
    organization = Organization(**payload.model_dump())
    db.add(organization)
    db.flush()
    record_audit(db, action="organization.create", resource_type="organization", resource_id=str(organization.id))
    db.commit()
    db.refresh(organization)
    return organization


@router.get("/organizations", response_model=list[OrganizationResponse])
async def list_organizations(db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    _require_admin(principal)
    return db.query(Organization).order_by(Organization.created_at.desc()).all()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require_admin(principal)
    user = User(**payload.model_dump())
    db.add(user)
    db.flush()
    record_audit(db, action="user.create", resource_type="user", resource_id=str(user.id))
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserResponse])
async def list_users(db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    _require_admin(principal)
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require_admin(principal)
    group = Group(**payload.model_dump())
    db.add(group)
    db.flush()
    record_audit(db, action="group.create", resource_type="group", resource_id=str(group.id))
    db.commit()
    db.refresh(group)
    return group


@router.get("/groups", response_model=list[GroupResponse])
async def list_groups(db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    _require_admin(principal)
    return db.query(Group).order_by(Group.created_at.desc()).all()


@router.post("/groups/{group_id}/members", response_model=dict, status_code=status.HTTP_201_CREATED)
async def add_group_member(
    group_id: int,
    payload: MembershipCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require_admin(principal)
    if payload.user_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="user_id is required")
    _get_or_404(db, Group, group_id, "Group")
    _get_or_404(db, User, payload.user_id, "User")
    membership = GroupMember(group_id=group_id, user_id=payload.user_id, role=payload.role)
    db.add(membership)
    db.flush()
    record_audit(db, action="group.member.add", resource_type="group", resource_id=str(group_id))
    db.commit()
    return {"id": membership.id, "group_id": group_id, "user_id": payload.user_id, "role": payload.role}


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require_admin(principal)
    project = Project(**payload.model_dump())
    db.add(project)
    db.flush()
    record_audit(db, action="project.create", resource_type="project", resource_id=str(project.id))
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.role in ADMIN_ROLES:
        return db.query(Project).order_by(Project.created_at.desc()).all()
    return db.query(Project).filter(Project.visibility == "organization").order_by(Project.created_at.desc()).all()


@router.post("/projects/{project_id}/members", response_model=dict, status_code=status.HTTP_201_CREATED)
async def add_project_member(
    project_id: int,
    payload: MembershipCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require_admin(principal)
    if not payload.user_id and not payload.group_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="user_id or group_id is required")
    _get_or_404(db, Project, project_id, "Project")
    if payload.user_id:
        _get_or_404(db, User, payload.user_id, "User")
    if payload.group_id:
        _get_or_404(db, Group, payload.group_id, "Group")
    membership = ProjectMember(project_id=project_id, user_id=payload.user_id, group_id=payload.group_id, role=payload.role)
    db.add(membership)
    db.flush()
    record_audit(db, action="project.member.add", resource_type="project", resource_id=str(project_id))
    db.commit()
    return {
        "id": membership.id,
        "project_id": project_id,
        "user_id": payload.user_id,
        "group_id": payload.group_id,
        "role": payload.role,
    }
