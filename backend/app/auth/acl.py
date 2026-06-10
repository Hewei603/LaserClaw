"""Project-level access control helpers."""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ExperimentCase, GroupMember, ProjectMember
from .security import Principal


ADMIN_ROLES = {"admin"}
REVIEWER_ROLES = {"admin", "reviewer"}
PROJECT_ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}


def _acl_enabled(principal: Principal) -> bool:
    return bool(principal.user_id is not None or get_settings().require_auth)


def is_admin(principal: Principal) -> bool:
    return principal.role in ADMIN_ROLES


def can_manage_knowledge(principal: Principal) -> bool:
    return not _acl_enabled(principal) or principal.role in REVIEWER_ROLES


def _user_group_ids(db: Session, user_id: int) -> list[int]:
    return [row[0] for row in db.query(GroupMember.group_id).filter(GroupMember.user_id == user_id).all()]


def project_role(db: Session, project_id: int | None, principal: Principal) -> str | None:
    if project_id is None or principal.user_id is None:
        return None
    group_ids = _user_group_ids(db, principal.user_id)
    query = db.query(ProjectMember).filter(ProjectMember.project_id == project_id)
    conditions = [ProjectMember.user_id == principal.user_id]
    if group_ids:
        conditions.append(ProjectMember.group_id.in_(group_ids))
    memberships = query.filter(or_(*conditions)).all()
    best: str | None = None
    for item in memberships:
        if best is None or PROJECT_ROLE_RANK.get(item.role, 0) > PROJECT_ROLE_RANK.get(best, 0):
            best = item.role
    return best


def has_project_role(db: Session, project_id: int | None, principal: Principal, minimum_role: str) -> bool:
    role = project_role(db, project_id, principal)
    return PROJECT_ROLE_RANK.get(role or "", 0) >= PROJECT_ROLE_RANK[minimum_role]


def can_view_case(db: Session, case: ExperimentCase, principal: Principal) -> bool:
    if not _acl_enabled(principal) or is_admin(principal):
        return True
    if principal.user_id is not None and case.owner_id == principal.user_id:
        return True
    if case.visibility == "organization":
        return True
    if case.visibility == "project":
        return has_project_role(db, case.project_id, principal, "viewer")
    return False


def can_edit_case(db: Session, case: ExperimentCase, principal: Principal) -> bool:
    if not _acl_enabled(principal) or is_admin(principal):
        return True
    if principal.user_id is not None and case.owner_id == principal.user_id:
        return True
    return case.visibility == "project" and has_project_role(db, case.project_id, principal, "editor")


def can_delete_case(db: Session, case: ExperimentCase, principal: Principal) -> bool:
    if not _acl_enabled(principal) or is_admin(principal):
        return True
    if principal.user_id is not None and case.owner_id == principal.user_id:
        return True
    return case.visibility == "project" and has_project_role(db, case.project_id, principal, "owner")


def assert_case_view(db: Session, case: ExperimentCase, principal: Principal) -> None:
    if not can_view_case(db, case, principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Case access denied")


def assert_case_edit(db: Session, case: ExperimentCase, principal: Principal) -> None:
    if not can_edit_case(db, case, principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Case edit access denied")


def assert_case_delete(db: Session, case: ExperimentCase, principal: Principal) -> None:
    if not can_delete_case(db, case, principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Case delete access denied")


def accessible_case_ids(db: Session, principal: Principal) -> list[int] | None:
    """Return visible case IDs, or None when ACL is intentionally open."""
    if not _acl_enabled(principal) or is_admin(principal):
        return None
    user_id = principal.user_id
    if user_id is None:
        return []
    group_ids = _user_group_ids(db, user_id)
    project_member_query = db.query(ProjectMember.project_id).filter(ProjectMember.user_id == user_id)
    if group_ids:
        project_member_query = project_member_query.union(
            db.query(ProjectMember.project_id).filter(ProjectMember.group_id.in_(group_ids))
        )
    project_ids = [row[0] for row in project_member_query.all()]
    query = db.query(ExperimentCase.id).filter(
        (ExperimentCase.owner_id == user_id) | (ExperimentCase.visibility == "organization")
    )
    if project_ids:
        query = query.union(
            db.query(ExperimentCase.id).filter(
                ExperimentCase.visibility == "project",
                ExperimentCase.project_id.in_(project_ids),
            )
        )
    return [row[0] for row in query.all()]
