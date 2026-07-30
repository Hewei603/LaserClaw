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


def resolve_condition(parsed: str | None, manual: str | None) -> str:
    """A human verdict outranks whatever the workbook text implied.

    Defined once, here, because two consumers need the same precedence: the ORM
    property below and the evaluator, which is also called with lightweight test
    doubles that carry no manual column at all.
    """
    return manual or parsed or "ok"


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
    condition = Column(String(50), default="ok", index=True)  # ok|damaged|uncertain — PARSED from the workbook
    # A person marking a mirror as broken must not have that erased by the next
    # import: the importer recomputes `condition` from the spreadsheet text every
    # time, so a human verdict needs somewhere the importer never writes.
    condition_manual = Column(String(50), nullable=True, index=True)  # ok|damaged|uncertain
    condition_note = Column(Text, nullable=True)
    condition_marked_by = Column(String(255), nullable=True)
    condition_marked_at = Column(DateTime(timezone=True), nullable=True)
    source_file = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    coatings = relationship("CoatingSpec", back_populates="item", cascade="all, delete-orphan")
    loans = relationship("InventoryLoan", back_populates="item", cascade="all, delete-orphan")

    @property
    def effective_condition(self) -> str:
        return resolve_condition(self.condition, self.condition_manual)


class InventoryLoan(Base):
    """One borrowing of an inventory item; open while ``returned_at`` is NULL.

    A separate table rather than fields on the item, because one item row can
    have a quantity of three and be signed out by three different people. It also
    keeps the history: "who had it last time it came back broken" is exactly the
    question a lab asks, and it is unanswerable if returning deletes the record.

    ``InventoryItem.quantity`` is deliberately never decremented — the importer
    overwrites it from the workbook on every re-import, so any bookkeeping stored
    there would be silently reverted. Availability is derived instead.
    """

    __tablename__ = "inventory_loans"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False, index=True)
    # Local single-user mode has no authentication, so user_id is usually NULL.
    # The typed-in name is what actually answers "who has it".
    borrower_name = Column(String(255), nullable=False)
    borrower_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    quantity = Column(Float, default=1, nullable=False)
    purpose = Column(Text, nullable=True)
    borrowed_at = Column(DateTime(timezone=True), server_default=func.now())
    expected_return_at = Column(DateTime(timezone=True), nullable=True)
    returned_at = Column(DateTime(timezone=True), nullable=True, index=True)
    returned_note = Column(Text, nullable=True)

    item = relationship("InventoryItem", back_populates="loans")


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
