# RAG Eval Datasets

LaserClaw uses JSONL datasets for retrieval quality and abstention checks.

## Public Example

`docs/evals/examples/rag_eval_synthetic.jsonl` is a small synthetic dataset for validating dataset loader and documentation wiring. It is safe to commit, but it is not evidence for real laboratory retrieval quality.

Validate it with:

```powershell
cd backend
py -c "from app.evals.datasets import load_jsonl_dataset; print(len(load_jsonl_dataset('../docs/evals/examples/rag_eval_synthetic.jsonl')))"
```

## Private Authorized Evals

Store real permissioned eval files under `docs/evals/private/`. That directory is ignored by Git except for `.gitkeep`.

Recommended files:

- `rag_eval_authorized_tuning.jsonl`
- `rag_eval_authorized_holdout.jsonl`
- `last_report.json`

Each JSONL row must include:

- `id`: stable string id.
- `query`: retrieval query string.

Optional fields:

- `case_id`: integer case scope.
- `should_answer`: boolean, default `true`.
- `expected_source_ids`: list of integer source ids.
- `expected_source_title_contains`: string title substring.
- `expected_terms`: list of strings that should appear in retrieved snippets.

The loader validates these field types before running retrieval, so malformed private datasets fail before producing misleading metrics.

Minimum acceptance targets for the holdout set:

- Positive hit rate: `>= 0.85`.
- Negative rejection rate: `>= 0.90`.
- Mean MRR: reviewed against the source mix and documented before release.

Run:

```powershell
cd backend
py scripts\eval_authorized_rag.py `
  --dataset ..\docs\evals\private\rag_eval_authorized_holdout.jsonl `
  --top-k 5 `
  --min-positive-hit-rate 0.85 `
  --min-negative-rejection-rate 0.90 `
  --output ..\docs\evals\private\last_report.json
```

When thresholds are provided, the command exits with code `2` if the holdout set does not meet the configured acceptance gate.

The final release audit reads `docs/evals/private/last_report.json`, so keep the latest passing holdout report at that path in the target environment.
