"""Structured optics inventory (L0) and deterministic component evaluator (L1).

- :mod:`app.inventory.parser`    — coating-string / geometry grammar parser
- :mod:`app.inventory.importer`  — xlsx workbook -> normalized inventory rows
- :mod:`app.inventory.evaluator` — requirement spec -> per-candidate structured
  verdicts (typed per-parameter operators, hard-fail veto, dominance ranking)
"""
