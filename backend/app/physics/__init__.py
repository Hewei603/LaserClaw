"""LaserClaw physics kernel.

Pure, deterministic scientific computing for laser-lab workflows:

- :mod:`app.physics.materials`  — refractive-index dispersion (Sellmeier & friends)
- :mod:`app.physics.tmm`        — thin-film transfer-matrix (characteristic matrix) solver
- :mod:`app.physics.archetypes` — standard coating archetype stacks + stopband estimates
- :mod:`app.physics.coating_tool` — dual-mode coating evaluation entrypoint
- :mod:`app.physics.beam`       — ABCD ray/Gaussian beam propagation and cavity modes
- :mod:`app.physics.nonlinear`  — birefringent phase matching, walk-off, SHG/SFG helpers

Design rules (do not break):

1. numpy only — no scipy, no FastAPI/SQLAlchemy/LLM imports.  This package must
   stay importable in the lean production image and usable as a standalone lib.
2. Deterministic and offline — all material data is bundled; no network calls.
3. Honest about uncertainty — functions return explicit confidence markers and
   assumptions instead of silently guessing (e.g. archetype coating estimates).
4. Clean-room physics — every formula derives from public textbook physics
   (Born & Wolf, Siegman "Lasers", Kogelnik & Li 1966, Macleod "Thin-Film
   Optical Filters", Boyd "Nonlinear Optics").  No third-party GPL code.
"""

__all__ = [
    "materials",
    "tmm",
    "archetypes",
    "coating_tool",
    "beam",
    "nonlinear",
]
