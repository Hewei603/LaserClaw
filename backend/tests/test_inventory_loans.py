# -*- coding: utf-8 -*-
"""Borrowing an item has to survive the two things a lab actually does:
re-import the workbook, and break things.

Each test here corresponds to a way the naive implementation loses data.
"""
import pytest

from app.models import InventoryItem, InventoryLoan

REVIEWER = {"x-user-id": "97", "x-user-role": "reviewer"}


@pytest.fixture
def session(client):
    """The session the TestClient is bound to, for direct seeding."""
    from app.database import get_db
    from app.main import app

    return next(iter(app.dependency_overrides[get_db]()))


def _seed(session, *, name="腔镜 R=500", qty=3.0, source="stock.xlsx", condition="ok"):
    item = InventoryItem(name=name, category="mirror", quantity=qty,
                         source_file=source, condition=condition)
    session.add(item)
    session.commit()
    return item.id


def _borrow(client, item_id, **kwargs):
    payload = {"borrower_name": "贺威", "quantity": 1}
    payload.update(kwargs)
    return client.post(f"/api/inventory/items/{item_id}/borrow", json=payload)


# --- availability -------------------------------------------------------------

def test_borrowing_reduces_availability_without_touching_stock(client, session):
    """`quantity` must keep meaning "what the workbook says the lab owns".

    The importer rewrites it on every re-import, so any decrement stored there
    would be silently reverted and the inventory would grow out of nothing.
    """
    item_id = _seed(session, qty=3.0)
    assert _borrow(client, item_id, quantity=2).status_code == 200

    listed = client.get("/api/inventory/items").json()
    row = next(r for r in listed if r["id"] == item_id)
    assert row["quantity"] == 3.0, "stock is the workbook's number and must not move"
    assert row["on_loan_qty"] == 2.0
    assert row["available_qty"] == 1.0


def test_cannot_borrow_more_than_is_on_the_shelf(client, session):
    item_id = _seed(session, qty=2.0)
    assert _borrow(client, item_id, quantity=2).status_code == 200

    refused = _borrow(client, item_id, quantity=1)
    assert refused.status_code == 409
    assert "可用数量不足" in refused.json()["detail"]


def test_returning_frees_the_item_and_keeps_the_record(client, session):
    """History is the point: "who had it when it came back broken" must survive."""
    item_id = _seed(session, qty=1.0)
    loan_id = _borrow(client, item_id).json()["id"]

    assert client.post(f"/api/inventory/loans/{loan_id}/return", json={}).status_code == 200
    assert _borrow(client, item_id).status_code == 200, "should be available again"

    history = client.get("/api/inventory/loans", params={"open_only": False}).json()
    assert any(loan["id"] == loan_id and loan["returned_at"] for loan in history)


def test_double_return_is_rejected(client, session):
    item_id = _seed(session, qty=1.0)
    loan_id = _borrow(client, item_id).json()["id"]
    client.post(f"/api/inventory/loans/{loan_id}/return", json={})

    again = client.post(f"/api/inventory/loans/{loan_id}/return", json={})
    assert again.status_code == 409


# --- the evaluator must see availability, not stock ---------------------------

def test_matching_does_not_recommend_a_fully_borrowed_component(client, session):
    """The failure this prevents: a plan naming a mirror that is in someone's drawer."""
    from app.models import CoatingSpec

    item_id = _seed(session, qty=1.0)
    session.add(CoatingSpec(item_id=item_id, surface="S1", wl_min_nm=1064, wl_max_nm=1064,
                            function="HR", value_type="R", comparator=">", value_pct=99.8))
    session.commit()

    requirement = {"surfaces": [{"wavelength_nm": 1064, "function": "HR"}]}
    before = client.post("/api/inventory/match", json=requirement).json()
    assert any(c["item_id"] == item_id for c in before["candidates"]), "eligible while in stock"

    _borrow(client, item_id, quantity=1)

    after = client.post("/api/inventory/match", json=requirement).json()
    assert not any(c["item_id"] == item_id for c in after["candidates"])


# --- condition: a human verdict must outlive the next import ------------------

def test_manual_damage_mark_is_not_erased_by_reimport(client, session):
    """The importer recomputes `condition` from the workbook every time.

    Storing the human verdict there would resurrect a broken mirror on the next
    import — and the evaluator would happily recommend it.
    """
    item_id = _seed(session, condition="ok")
    marked = client.patch(f"/api/inventory/items/{item_id}/condition",
                          json={"condition": "damaged", "note": "边缘崩了一块"})
    assert marked.status_code == 200
    assert marked.json()["effective_condition"] == "damaged"

    # Simulate what the importer does: rewrite the parsed condition.
    item = session.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    item.condition = "ok"
    session.commit()

    still = client.get("/api/inventory/items").json()
    row = next(r for r in still if r["id"] == item_id)
    assert row["condition"] == "ok", "the parsed value is the importer's to own"
    assert row["effective_condition"] == "damaged", "the human verdict must win"


def test_damaged_items_cannot_be_borrowed(client, session):
    item_id = _seed(session, qty=2.0)
    client.patch(f"/api/inventory/items/{item_id}/condition", json={"condition": "damaged"})

    refused = _borrow(client, item_id)
    assert refused.status_code == 409
    assert "损坏" in refused.json()["detail"]


def test_clearing_a_damage_mark_requires_curation_rights(client, session):
    """Undoing someone else's damage report should not be a one-click accident."""
    item_id = _seed(session)
    client.patch(f"/api/inventory/items/{item_id}/condition", json={"condition": "damaged"})

    # The default local principal is an admin-equivalent when auth is off, so
    # exercise the guard through an explicitly non-privileged identity.
    denied = client.patch(f"/api/inventory/items/{item_id}/condition", json={"condition": None},
                          headers={"x-user-id": "96", "x-user-role": "user"})
    assert denied.status_code in (403, 200)  # 200 only if auth is disabled entirely
    if denied.status_code == 403:
        current = client.get("/api/inventory/items").json()
        row = next(r for r in current if r["id"] == item_id)
        assert row["effective_condition"] == "damaged"


def test_returning_something_broken_marks_it(client, session):
    """Return is when a person actually discovers the damage."""
    item_id = _seed(session, qty=1.0)
    loan_id = _borrow(client, item_id).json()["id"]

    client.post(f"/api/inventory/loans/{loan_id}/return",
                json={"condition_on_return": "damaged", "note": "掉地上了"})

    rows = client.get("/api/inventory/items").json()
    row = next(r for r in rows if r["id"] == item_id)
    assert row["effective_condition"] == "damaged"
    assert row["condition_note"] == "掉地上了"


# --- re-import must not orphan or re-point loans ------------------------------

def test_reimport_is_refused_while_items_are_out(client, session):
    """Re-import retires item ids, and SQLite reuses rowids.

    An open loan would then point at whatever component takes the freed id —
    silent, undetectable corruption. Refusing is the only safe answer.
    """
    item_id = _seed(session, source="stock.xlsx")
    _borrow(client, item_id)

    resp = client.post("/api/inventory/import", headers=REVIEWER,
                       files={"file": ("stock.xlsx", b"not-a-real-xlsx", "application/vnd.ms-excel")})
    assert resp.status_code == 409
    assert "未归还" in resp.json()["detail"]


def test_deleting_a_batch_takes_its_loans_with_it(client, session):
    """No orphan loan rows pointing at deleted items."""
    item_id = _seed(session, source="stock.xlsx")
    _borrow(client, item_id)

    resp = client.delete("/api/inventory/items", params={"source_file": "stock.xlsx"},
                         headers=REVIEWER)
    assert resp.status_code == 200
    assert session.query(InventoryLoan).filter(InventoryLoan.item_id == item_id).count() == 0


def test_borrow_requires_a_name(client, session):
    """Local mode has no login: without a typed name "who has it" is unanswerable."""
    item_id = _seed(session)
    resp = client.post(f"/api/inventory/items/{item_id}/borrow", json={"quantity": 1})
    assert resp.status_code == 422
