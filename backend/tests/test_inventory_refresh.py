"""Actual XLSX round trips must retain physical-item state and history."""
from io import BytesIO

from openpyxl import Workbook


def _upload(client, rows, filename="refresh.xlsx"):
    workbook = Workbook()
    workbook.active.append(["id", "name", "S1", "S2", "size", "ROC", "quantity", "location", "keeper", "vendor"])
    for index, (name, roc, quantity, location) in enumerate(rows, 1):
        workbook.active.append([index, name, "1064HR", "", "D=25.4mm", roc, quantity, location, "", ""])
    data = BytesIO()
    workbook.save(data)
    workbook.close()
    return client.post("/api/inventory/import", files={"file": (filename, data.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


def _items(client):
    return client.get("/api/inventory/items").json()


def _damage_with_history(client, item):
    loan = client.post(f"/api/inventory/items/{item['id']}/borrow",
                       json={"borrower_name": "Test borrower", "quantity": 1}).json()
    response = client.post(f"/api/inventory/loans/{loan['id']}/return",
                           json={"condition_on_return": "damaged", "note": "Recorded chip"})
    assert response.status_code == 200, response.text
    return loan["id"]


def test_reimport_preserves_ids_damage_and_history_after_sorting(client):
    assert _upload(client, [("Mirror A", "R=500mm", 1, "Shelf A"), ("Mirror B", "R=200mm", 2, "Shelf B")]).status_code == 200
    old = {item["name"]: item for item in _items(client)}
    loan_id = _damage_with_history(client, old["Mirror A"])
    response = _upload(client, [("Mirror B", "R=200mm", 4, "New shelf"), ("Mirror A", "R=500mm", 1, "Shelf A")])
    assert response.status_code == 200, response.text
    new = {item["name"]: item for item in _items(client)}
    assert len(new) == 2
    assert new["Mirror A"]["id"] == old["Mirror A"]["id"]
    assert new["Mirror B"]["id"] == old["Mirror B"]["id"]
    assert new["Mirror A"]["effective_condition"] == "damaged"
    assert new["Mirror A"]["condition_note"] == "Recorded chip"
    assert new["Mirror B"]["quantity"] == 4
    assert new["Mirror B"]["location"] == "New shelf"
    assert len(new["Mirror A"]["coatings"]) == 1
    history = client.get("/api/inventory/loans?open_only=false").json()
    assert [loan["id"] for loan in history] == [loan_id]
    refused = client.post(f"/api/inventory/items/{old['Mirror A']['id']}/borrow",
                          json={"borrower_name": "Next borrower", "quantity": 1})
    assert refused.status_code == 409


def test_removed_item_history_is_retained_with_zero_stock_and_restored_on_reappearance(client):
    _upload(client, [("Mirror A", "R=500mm", 1, "A"), ("Mirror B", "R=200mm", 1, "B")])
    item = next(item for item in _items(client) if item["name"] == "Mirror A")
    loan_id = _damage_with_history(client, item)
    assert _upload(client, [("Mirror B", "R=200mm", 1, "B")]).status_code == 200
    retired = next(row for row in _items(client) if row["id"] == item["id"])
    assert retired["quantity"] == 0
    assert retired["effective_condition"] == "damaged"
    assert client.get("/api/inventory/loans?open_only=false").json()[0]["id"] == loan_id
    assert _upload(client, [("Mirror A", "R=500mm", 1, "A"), ("Mirror B", "R=200mm", 1, "B")]).status_code == 200
    restored = next(row for row in _items(client) if row["id"] == item["id"])
    assert restored["quantity"] == 1 and restored["effective_condition"] == "damaged"


def test_spec_edit_with_human_history_is_atomic_conflict(client):
    _upload(client, [("Mirror A", "R=500mm", 1, "A")])
    item = _items(client)[0]
    _damage_with_history(client, item)
    response = _upload(client, [("Mirror A", "R=200mm", 5, "B")])
    assert response.status_code == 409, response.text
    current = _items(client)
    assert len(current) == 1
    assert current[0]["id"] == item["id"] and current[0]["roc_mm"] == 500
    assert current[0]["effective_condition"] == "damaged"


def test_identical_duplicate_rows_do_not_transfer_a_damage_verdict(client):
    rows = [("Mirror A", "R=500mm", 1, "A"), ("Mirror A", "R=500mm", 1, "A")]
    _upload(client, rows)
    item = _items(client)[0]
    _damage_with_history(client, item)
    response = _upload(client, rows)
    assert response.status_code == 409, response.text
    assert len(_items(client)) == 2


def test_duplicate_specs_with_distinct_locations_keep_their_own_history(client):
    rows = [("Mirror A", "R=500mm", 1, "Shelf A"), ("Mirror A", "R=500mm", 1, "Shelf B")]
    _upload(client, rows)
    old = {item["location"]: item for item in _items(client)}
    _damage_with_history(client, old["Shelf A"])
    response = _upload(client, list(reversed(rows)))
    assert response.status_code == 200, response.text
    new = {item["location"]: item for item in _items(client)}
    assert new["Shelf A"]["id"] == old["Shelf A"]["id"]
    assert new["Shelf A"]["effective_condition"] == "damaged"
    assert new["Shelf B"]["id"] == old["Shelf B"]["id"]
    assert new["Shelf B"]["effective_condition"] == "ok"


def test_invalid_workbook_does_not_change_existing_inventory(client):
    _upload(client, [("Mirror A", "R=500mm", 1, "A")])
    item = _items(client)[0]
    _damage_with_history(client, item)
    before = _items(client)
    response = client.post("/api/inventory/import", files={"file": ("refresh.xlsx", b"invalid workbook", "application/octet-stream")})
    assert response.status_code == 400
    assert _items(client) == before
    assert len(client.get("/api/inventory/loans?open_only=false").json()) == 1
