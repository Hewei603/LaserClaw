"""Case module models for optional experiment workflows."""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class CaseModule(Base):
    """A user-enabled workflow module attached to one experiment case."""

    __tablename__ = "case_modules"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("experiment_cases.id"), nullable=False, index=True)
    module_type = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    status = Column(String(50), default="draft", index=True)
    config_json = Column(JSON, default=dict)
    result_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    case = relationship("ExperimentCase", back_populates="case_modules")
    files = relationship("CaseModuleFile", back_populates="module", cascade="all, delete-orphan")
    component_items = relationship("CaseComponentItem", back_populates="module", cascade="all, delete-orphan")


class CaseModuleFile(Base):
    """Input or output file owned by a case module."""

    __tablename__ = "case_module_files"

    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("case_modules.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(1024), nullable=False)
    file_type = Column(String(100))
    file_role = Column(String(50), default="input", index=True)
    content_hash = Column(String(64), index=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    module = relationship("CaseModule", back_populates="files")


class CaseComponentItem(Base):
    """One item in a per-case component or procurement list."""

    __tablename__ = "case_component_items"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("experiment_cases.id"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("case_modules.id"), nullable=True, index=True)
    category = Column(String(80), default="component", index=True)
    name = Column(String(255), nullable=False)
    specification = Column(Text)
    quantity = Column(Float, default=1)
    unit = Column(String(50), default="pcs")
    purpose = Column(Text)
    required = Column(Boolean, default=True)
    owned = Column(Boolean, default=False, index=True)
    procurement_status = Column(String(50), default="needed", index=True)
    vendor = Column(String(255))
    part_number = Column(String(255))
    notes = Column(Text)
    source = Column(String(50), default="manual", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    case = relationship("ExperimentCase", back_populates="component_items")
    module = relationship("CaseModule", back_populates="component_items")
