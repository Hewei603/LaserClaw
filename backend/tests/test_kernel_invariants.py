# -*- coding: utf-8 -*-
"""Invariants that keep the kernel's core promises from silently decaying.

Both tests here exist because the promise they guard was previously kept by a
human remembering to check — and a promise nobody checks is a promise that
degrades on the next refactor.
"""
import ast
from pathlib import Path

from app.physics.design import design_linear_cavity

PHYSICS_DIR = Path(__file__).resolve().parents[1] / "app" / "physics"

# The kernel's whole value is that it computes rather than asks a model, so it
# must not reach for a model, the network, or the database. numpy and the
# standard library are the entire allowance.
FORBIDDEN_ROOTS = {
    "openai", "anthropic",                        # LLM SDKs
    "httpx", "requests", "urllib", "aiohttp",     # network
    "sqlalchemy", "alembic", "psycopg2",          # ORM / DB
    "fastapi", "starlette", "pydantic",           # web layer
    "chromadb", "sentence_transformers",          # embedding stacks
}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import inside app.physics itself.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_physics_kernel_imports_nothing_forbidden():
    """The kernel stays a pure library: no LLM, no network, no ORM, no web.

    Asserted structurally (AST over every module) rather than by reading the
    imports once, so adding `import sqlalchemy` to any physics module fails
    here instead of quietly coupling the kernel to the application.
    """
    offenders = []
    for module in sorted(PHYSICS_DIR.glob("*.py")):
        forbidden = _imported_roots(module) & FORBIDDEN_ROOTS
        if forbidden:
            offenders.append(f"{module.name}: {sorted(forbidden)}")
    assert not offenders, "physics kernel must stay dependency-free: " + "; ".join(offenders)


def test_design_search_space_size_is_stable():
    """The advertised search space is a property of the defaults, not a memory.

    geometries_evaluated is fully determined by the candidate ROC list and the
    length sweep (12 radii -> 77 usable pairs x 157 lengths). Quoting the
    number anywhere (docs, a report, a CV) is only safe if a test pins it, so a
    tuning change to DEFAULT_CANDIDATE_ROCS or the sweep shows up here first.
    """
    result = design_linear_cavity(wavelength_nm=1064.0)
    assert result["search_space"]["geometries_evaluated"] == 12089

    # The stable-solution count depends on the cavity contents, so it is only
    # meaningful when quoted together with its configuration.
    empty_cavity = result["search_space"]["stable_configurations_found"]
    with_crystal = design_linear_cavity(
        wavelength_nm=1064.0,
        crystal={"n": 1.8147, "thickness_mm": 10, "position_mm": 20},
    )["search_space"]["stable_configurations_found"]
    assert empty_cavity == 4379
    assert with_crystal == 4323
    assert empty_cavity != with_crystal, "the count is configuration-dependent by construction"
