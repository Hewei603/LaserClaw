# Task-led laboratory Agent (LaserClaw 2.0)

LaserClaw's primary workflow starts with a task, not a cavity template. Rezonator is an optical calculation tool that an Agent can choose; it does not define the application's task types. The current executable optical adapter uses the project's Python/NumPy ABCD implementation. A Rezonator C++ runtime adapter is **not connected**.

## User workflow

Create a case with a title and description, then use **Agent 工作区**. Describe whatever is available: a goal, installed/owned parts, constraints, measurements, or unresolved observations. Attach images, PDF/text/CSV files or XLSX tables. The Agent can inspect the case, earlier conversation, saved tool outputs, artifacts and actual inventory.

The Agent decides which available tool to call and inspects its return value before choosing the next action. This supports combined tasks: retrieve a previous layout, independently recalculate it, scan a spacing, compare the result and ask for a measurement that resolves the remaining uncertainty. Users do not have to select the appropriate physics module themselves.

Results distinguish four outcomes:

- `completed`: the requested deliverable has been produced within its stated model scope.
- `partial`: useful results exist and work remains.
- `needs_input`: a user answer is necessary. Each question includes its purpose, a way to obtain the information and the expected units/format.
- `unsupported`: the required capability is absent, with a concrete alternative or next step.

A reply starts another run in the same conversation, including previous questions and saved results. Tool inputs, outputs, errors, timing and final artifacts persist. Model/network failure preserves successful tool outputs and creates a partial result. Stop prevents later model responses from triggering new calls; an already executing request can take until its timeout to settle. The local runner is not a distributed job queue.

If a model labels a result `completed` while also asking required questions, the service conservatively normalizes it to `partial` (when successful tool results exist) or `needs_input`. This preserves the useful answer without spending another model call to repair only its status. Evidence references still require successful, recorded tool calls.

## Available capabilities

| Capability | Implemented scope | Boundary |
| --- | --- | --- |
| General optical system | Single-pass, standing-wave and coplanar ring ABCD; T/S planes; thin lenses/mirrors, flat media, normal-incidence thick lenses, focusing quadratic GRIN, real symplectic custom matrices; single-pass equivalent M² | Paraxial, common T/S axes. Cavity eigenmode remains M²=1. No non-coplanar rotation, anisotropic crystal propagation, aperture diffraction or power prediction |
| Parameter scan | One-parameter sampled intervals and two-parameter T/S stability maps; length, focal length, curvature, index, GRIN coefficient or angle | Bounded finite grid; no global optimality certificate |
| Specialized laser design | End-pumped two-mirror layout; either input or output may be flat/concave; crystal sections, owned constraints, nearby spacing candidates and detailed analysis | Optional design tool. Unknown curved-input substrate leaves pump placement as an explicitly incomplete baseline |
| Editable optical project | Version history, element identities, owned-part locks, inventory bindings, stored numerical analysis, saved 2D scans and exports | Every save appends a revision; stale saves rejected. Pump transmission and cavity models are scoped separately |
| Measured caustic | Fit air beam radii vs z for waist position/radius, divergence and equivalent M², with fit-quality checks | Requires actual data and radius convention; not ISO certification or a multimode field reconstruction |
| Power curve | Measured threshold and slope fit, fit quality, warnings, incident/absorbed/nominal pump basis | Does not invent measurements or predict an unmeasured laser's power |
| Phase matching | Existing BBO/LBO/KTP/BiBO SHG/SFG solver | No full nonlinear conversion or thermal field simulation |
| Coating | Existing exact stack TMM, supplied R/T curve, explicitly labeled nominal archetype | A nominal coating label cannot establish actual off-design reflectivity |
| Inventory | Available quantity, specifications and deterministic candidate matching | Missing or uncertain specifications remain visible; no invented products or stock |
| Evidence | Attachments, stored case/artifact/tool results, local knowledge, OpenAlex/arXiv metadata/abstracts | External retrieval depends on configured services; no claim to read full text from metadata |

The general optical output has zoomable T/S radius plots, per-element coordinates, SVG export and complete JSON calculation records. The existing saved plane-concave design retains its richer caustic/wavefront/stability analysis, precise cursor and CSV/SVG/PNG exports under **已存光路设计**. These two visualization scopes are not full Rezonator feature parity.

`analyze_saved_design` lets the Agent inspect exact analytic waists, element boundaries and thermal variants of an existing specialized design. Compact model context retains numerical extrema and labels any sampled series. The specialized thermal focal length is defined inside the crystal; the general thin-lens adapter uses an air-equivalent focal length, `f_air = f_inside / n`. Compare these calculations only after applying that conversion.

## Implementation

- `backend/app/workbench/tools.py`: one executable registry supplies tool discovery, validation schemas and dispatch. Add a capability here; do not add a keyword branch to the UI or orchestrator.
- `backend/app/workbench/service.py`: model → validated call → persisted real result → model loop. A maximum of 16 model turns / 32 executed tool calls bounds each run. Only `finish` ends a successful model turn; invalid output is returned for repair.
- `backend/app/workbench/contracts.py`: typed result/questions/evidence contracts. `needs_input` without an acquisition guide, or a fabricated tool evidence id, fails validation.
- `backend/app/workbench/optics.py`: typed application adapter around the dependency-free physics library. Distances are physical mm; wavelengths vacuum nm; radius is 1/e² intensity; propagation uses reduced q with explicit medium conversion.
- `backend/app/providers/tool_calling.py`: native OpenAI Responses, Anthropic Messages and configured Chat Completions-compatible provider adapters. Responses continuation preserves encrypted reasoning items and call ids with `store=false`.
- `backend/app/api/workbench.py`: case-scoped submit/read/stop APIs. Existing ACL rules are reused, not redesigned.
- `frontend/src/components/ExperimentWorkbench.jsx`: task input, conversation, results, actionable questions, tool traces and prior design artifacts.

No database migration: existing chat, task, step, tool-call and generated-content tables are reused. Old fixed module APIs and chat are retained as **旧版模块助手 / 旧版对话记录** for compatibility; new tasks use the workbench.

The **光学工程** tab is usable without a model request: expand element parameters, edit free geometry, save a new version and calculate a 2D map. Owned hardware requires an explicit unlock to change. Historical selection is read-only until saved as a new version; the revision's own scan is restored on reload. Element-table wavefront radii use the air-equivalent reference convention, while segment profiles use their physical medium.

`scripts/recalculate_design.py --case-id <id> --evidence <json> --output <json> [--write]` is an explicit operator fallback for an already supported linear design when a model service is unavailable. Quoted fact updates are validated against supplied source text. Default execution writes only a local numerical report; `--write` appends a clearly labeled direct-kernel run, design, optical project and stability map. It never claims that a real model completed that run. Preserve a database backup before using this operational command.

## Validation

Rezonator oracle tests read `calc/rezonator.py` from `REZONATOR_REFERENCE_DIR`, defaulting to the ignored `rezonator2-master/` checkout. Without that optional checkout, only those cross-checks skip locally; analytic kernel tests still run. CI checks out upstream commit `aa7e52725da5826eddd1891aee2e308e9390ba3e` and sets `REQUIRE_REZONATOR_REFERENCE=1`, so missing reference files fail CI rather than silently skipping validation. The upstream source is used as a test oracle and is not bundled into LaserClaw.

`backend/tests/test_optical_upgrade.py` adds analytic reversed-mirror references, asymmetric thick-lens forward/return checks, quarter-pitch GRIN, M² propagation, caustic fitting, 2D g-parameter maps, project locks/history/stale writes, and saved-scan reload/isolation. These deterministic checks do not replace a real configured-model acceptance run.

`backend/tests/test_workbench.py` exercises analytic Gaussian references, dielectric physical coordinates, a 4f relay, astigmatic ring/unstable cases, scans, input validation, iterative error repair, numerical evidence persistence, follow-up context, data fitting, file reads, unsupported results, cancellation, provider failure and Responses protocol continuation.

`backend/scripts/validate_workbench_live.py --live --output <report.json>` explicitly opts into real configured-model calls. It creates a temporary isolated database and exercises four distinct tasks: a 4f relay, synthetic measured-power fitting, an unsupported thermal/lifetime request, and a T/S ring-cavity scan. Its synthetic facts never enter the user's case database. Inspect both the reported tool executions and numerical outputs; a fluent answer alone is not a passing simulation.

An actual case-5 acceptance run additionally reads the user's saved layout and two attachments, checks inventory, and independently recalculates/scans the cavity. The result belongs to that case's run history.
