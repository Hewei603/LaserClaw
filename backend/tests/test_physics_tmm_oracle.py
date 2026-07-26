"""Cross-validate our TMM solver against the independent Byrnes `tmm` package.

The oracle is a dev-only dependency; this file skips cleanly when absent so the
production image and minimal CI environments are unaffected.
"""
import numpy as np
import pytest

oracle = pytest.importorskip("tmm")

from app.physics.tmm import solve_RT  # noqa: E402


def test_random_stacks_match_byrnes_oracle():
    rng = np.random.default_rng(7)
    worst = 0.0
    for _ in range(60):
        n_layers = int(rng.integers(0, 10))
        ns = [complex(1 + 2.5 * rng.random(), -0.3 * rng.random() * (rng.random() < 0.3))
              for _ in range(n_layers)]
        ds = [float(20 + 400 * rng.random()) for _ in range(n_layers)]
        nsub = complex(1.2 + 1.5 * rng.random(), -0.4 * rng.random() * (rng.random() < 0.4))
        wl = float(400 + 1300 * rng.random())
        aoi = float(rng.random() * 80)
        pol = ("s", "p")[int(rng.integers(0, 2))]

        R, T, A = solve_RT(np.array(ns, complex), np.array(ds, float), wl, aoi, pol, 1.0, nsub)
        # Byrnes tmm uses n + ik for loss; conjugate our n - ik inputs.
        res = oracle.coh_tmm(
            pol,
            [1.0] + [complex(n.real, -n.imag) for n in ns] + [complex(nsub.real, -nsub.imag)],
            [np.inf] + ds + [np.inf],
            np.deg2rad(aoi),
            wl,
        )
        worst = max(worst, abs(R - res["R"]), abs(T - res["T"]))
    assert worst < 1e-10, f"TMM diverges from independent oracle by {worst:.2e}"
