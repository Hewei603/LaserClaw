# LaserClaw project rules

## Product identity
LaserClaw is a vertical AI-agent application for laser experiment assistance.
It is an AI-assisted workflow system for:
- laser experiment planning
- ReZonator schema/template drafting
- symptom-based troubleshooting
- experiment case recording
- report generation
- lab knowledge accumulation

It is not a system for direct hardware control.
It is not allowed to pretend it can fully automate real laser alignment or replace human experimental judgment.

## Primary users
- me, a beginner in laser system setup and cavity experiments
- lab newcomers who need structured guidance
- senior students who want faster experiment recording and troubleshooting support

## MVP goal
Build a serious, local-first, GitHub-ready MVP that is good enough to publish as an open-source project after minor polishing.

## Definition of done
LaserClaw is NOT done unless all of the following are true:

1. The repository contains a clean, modular, documented codebase.
2. The app runs locally with Docker Compose.
3. There is a working FastAPI backend.
4. There is a working React frontend.
5. PostgreSQL is integrated correctly.
6. A user can create, view, edit, and delete experiment cases.
7. A user can input experiment goals, cavity type, key parameters, and observed symptoms.
8. The system can generate a structured experiment plan.
9. The system can generate a ReZonator schema/template draft.
10. The system can generate troubleshooting suggestions from symptoms.
11. The system can generate and save an experiment report.
12. Users can upload and view attachments such as notes, images, and schema-related files.
13. The repo includes seeded demo data for immediate local demonstration.
14. AI features support a mock/demo mode without requiring external API keys.
15. README includes project overview, architecture, setup, demo flow, screenshots/placeholders, and roadmap.
16. Core backend tests pass.

If any item is incomplete, do not stop.

## MVP scope
Must implement:
- experiment case management
- structured experiment intake
- experiment planning output
- ReZonator schema/template draft generation
- symptom-based troubleshooting
- report generation
- attachment upload and local storage
- seeded sample cases
- local demo-ready workflow
- mock AI mode

## Not in MVP
Do not build these now:
- direct hardware control
- instrument drivers
- automatic alignment
- closed-loop physical control
- hard claims of scientific certainty
- advanced multimodal physical diagnosis
- full multi-agent harness-style orchestration
- complicated auth or enterprise SSO
- cloud deployment requirements

Harness-style or more advanced agent orchestration can be added later.
Current MVP should prioritize a stable single-coordinator workflow with modular services.

## Engineering constraints
Use this stack unless there is a strong implementation reason not to:
- FastAPI backend
- React + Vite frontend
- PostgreSQL
- Docker Compose
- local file storage for attachments
- clear provider abstraction for AI features
- mock provider for demo mode
- pytest for backend tests

Keep architecture modular and practical.
Prefer stable working features over ambitious unfinished scope.
Do not overengineer.

## Domain rules
LaserClaw can assist with structure, reasoning, checklist generation, troubleshooting hypotheses, and report writing.
LaserClaw must not silently invent laser physics facts.
When domain logic is heuristic, label it clearly in code or UI as:
- heuristic
- draft
- assistant suggestion
- needs human verification

Do not present generated ReZonator schema/template output as experimentally validated.
Do not claim that troubleshooting suggestions are guaranteed correct.

## Required modules
Organize the code so that these capabilities are clear:
- experiment case management
- planner
- rezonator draft generator
- troubleshooting engine
- report generator
- attachment handling
- demo/mock AI provider

## Required workflow
1. Inspect the existing repository first.
2. Write a concrete implementation plan to `docs/implementation-plan.md`.
3. Implement in phases.
4. Update README continuously.
5. Keep commits small and meaningful.
6. Verify success criteria before stopping.

## Delivery preference
A narrow but fully working MVP is better than a broad broken system.
If blocked on one feature, continue all other features and document blockers in `docs/BLOCKERS.md`.
Do not stop early just because the structure looks complete.
Only stop when the repo is genuinely demoable and most remaining work is polish.