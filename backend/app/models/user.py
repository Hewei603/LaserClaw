"""Organization, user, and collaboration models."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class Organization(Base):
    """Tenant boundary for future multi-tenant deployments."""

    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="organization")
    projects = relationship("Project", back_populates="organization")
    groups = relationship("Group", back_populates="organization")


class User(Base):
    """Application user with a coarse RBAC role."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=False)
    role = Column(String(50), default="user", index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="users")
    agent_tasks = relationship("AgentTask", back_populates="user")
    group_memberships = relationship("GroupMember", back_populates="user", cascade="all, delete-orphan")
    project_memberships = relationship("ProjectMember", back_populates="user", cascade="all, delete-orphan")


class Group(Base):
    """Collaborator group inside an organization."""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="groups")
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    project_memberships = relationship("ProjectMember", back_populates="group", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_groups_org_name"),)


class GroupMember(Base):
    """User membership in a group."""

    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(50), default="member", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_memberships")

    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_members_group_user"),)


class Project(Base):
    """Long-lived research project that owns cases and permissions."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    visibility = Column(String(50), default="private", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    organization = relationship("Organization", back_populates="projects")
    cases = relationship("ExperimentCase", back_populates="project")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_projects_org_name"),)


class ProjectMember(Base):
    """User or group access grant for a project."""

    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True, index=True)
    role = Column(String(50), default="viewer", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="members")
    user = relationship("User", back_populates="project_memberships")
    group = relationship("Group", back_populates="project_memberships")
