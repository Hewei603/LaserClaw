import json

from app.evals.acceptance import (
    load_eval_report,
    summarize_final_acceptance,
    validate_eval_report,
    validate_github_ci_run,
)


def test_validate_eval_report_requires_passing_acceptance():
    report = {
        "summary": {"positive_hit_rate": 0.8, "negative_rejection_rate": 1.0},
        "acceptance": {
            "passed": False,
            "failures": [{"metric": "positive_hit_rate", "actual": 0.8, "threshold": 0.85}],
        },
    }

    result = validate_eval_report(report)

    assert result["passed"] is False
    assert result["failures"][0]["metric"] == "positive_hit_rate"


def test_validate_eval_report_accepts_threshold_pass(tmp_path):
    path = tmp_path / "last_report.json"
    path.write_text(
        json.dumps(
            {
                "summary": {"positive_hit_rate": 0.9, "negative_rejection_rate": 1.0},
                "acceptance": {"passed": True, "thresholds": {"min_positive_hit_rate": 0.85}},
            }
        ),
        encoding="utf-8",
    )

    result = validate_eval_report(load_eval_report(path))

    assert result["passed"] is True
    assert result["thresholds"]["min_positive_hit_rate"] == 0.85


def test_validate_github_ci_run_requires_success():
    failed = validate_github_ci_run({"name": "CI", "status": "completed", "conclusion": "failure"})
    passed = validate_github_ci_run({"name": "CI", "status": "completed", "conclusion": "success", "html_url": "https://example.test/run"})

    assert failed["passed"] is False
    assert passed["passed"] is True
    assert passed["html_url"] == "https://example.test/run"


def test_final_acceptance_requires_all_gates():
    summary = summarize_final_acceptance(
        local_passed=True,
        ci={"passed": True},
        private_eval={"passed": False, "reason": "missing report"},
    )

    assert summary["passed"] is False
    assert summary["gates"]["private_eval"]["reason"] == "missing report"
