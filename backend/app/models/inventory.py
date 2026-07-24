"""Structured optics inventory models (L0).

One :class:`InventoryItem` row = one physical component spec variant (a mirror
with a given ROC/coating, a crystal with a given cut).  Multi-band coatings are
exploded into per-surface per-band :class:`CoatingSpec` child rows so matching
is a SQL/rule problem, never free-text similarity.  Unknown values stay NULL and
are surfaced explicitly — never guessed.
"""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class InventoryItem(Base):
    """One physical component spec variant in the lab inventory."""

    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False, index=True)  # mirror|lens|gain_crystal|nonlinear_crystal|window|other
    name = Column(String(255), nullable=False, index=True)
    # geometry
    diameter_mm = Column(Float, nullable=True)
    roc_mm = Column(Float, nullable=True)          # concave positive; NULL = flat/unknown (see roc_is_flat)
    roc_is_flat = Column(Boolean, default=False)
    thickness_mm = Column(Float, nullable=True)
    dimensions = Column(String(100), nullable=True)  # e.g. "3*3*25mm3" for crystals
    # crystal-specific
    cut_angle_theta_deg = Column(Float, nullable=True)
    cut_angle_phi_deg = Column(Float, nullable=True)
    cut_axis = Column(String(50), nullable=True)     # e.g. "c-cut"; NULL = unknown
    doping_pct = Column(Float, nullable=True)
    material = Column(String(100), nullable=True)    # e.g. "Nd:YAG", "LBO"
    # logistics
    quantity = Column(Float, default=1)
    location = Column(String(100), nullable=True, index=True)
    keeper = Column(String(255), nullable=True)
    vendor = Column(String(255), nullable=True)
    # provenance / honesty
    raw_spec = Column(Text, nullable=True)           # original row text, always kept
    parse_confidence = Column(String(20), default="parsed", index=True)  # parsed|partial|needs_review
    parse_notes = Column(JSON, default=list)         # list of warnings ("切向未知", "裂纹", ...)
    condition = Column(String(50), default="ok", index=True)  # ok|damaged|uncertain
    source_file = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    coatings = relationship("CoatingSpec", back_populates="item", cascade="all, delete-orphan")


class CoatingSpec(Base):
    """One surface x wavelength-band coating entry of an inventory item.

    ``"S1:1064-1066HR, 1176-1180 T=20%"`` becomes two rows:
    ``(S1, 1064, 1066, HR, R, >, 99.5?)`` and ``(S1, 1176, 1180, PR, T, =, 20)``.
    Threshold fields stay NULL when the label carries no number.
    """

    __tablename__ = "coating_specs"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False, index=True)
    surface = Column(String(10), nullable=False, index=True)   # S1|S2|both
    wl_min_nm = Column(Float, nullable=False, index=True)
    wl_max_nm = Column(Float, nullable=False, index=True)
    function = Column(String(10), nullable=False, index=True)  # HR|AR|HT|PR (PR = partial reflector)
    value_type = Column(String(5), nullable=True)              # R|T
    comparator = Column(String(5), nullable=True)              # >|<|=
    value_pct = Column(Float, nullable=True)
    raw_fragment = Column(String(255), nullable=True)          # the exact source text fragment

    item = relationship("InventoryItem", back_populates="coatings")
