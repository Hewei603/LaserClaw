"""Tests for structured output schema validation and repair."""
from __future__ import annotations


from app.agent.schemas import (
    ExperimentPlanSchema,
    ExperimentReportSchema,
    TroubleshootingSchema,
    validate_and_repair,
    validate_artifact,
)


class TestExperimentPlanSchema:
    def test_full_valid_plan(self):
        data = {
            "objective": "Achieve 1064nm CW output",
            "setup": "Nd:YAG rod, pump diode, HR/OC mirrors",
            "steps": ["Align pump beam", "Optimize cavity"],
            "measurements": ["Output power", "Beam profile"],
            "risks": ["Eye hazard from 1064nm"],
            "next_actions": ["Measure M2"],
        }
        schema = ExperimentPlanSchema.model_validate(data)
        assert schema.objective == "Achieve 1064nm CW output"
        assert len(schema.steps) == 2

    def test_empty_steps_gets_repaired(self):
        data = {"objective": "Test", "setup": "Basic setup", "steps": []}
        schema = ExperimentPlanSchema.model_validate(data)
        assert len(schema.steps) == 1
        assert "please review" in schema.steps[0].lower()

    def test_missing_fields_use_defaults(self):
        schema = ExperimentPlanSchema.model_validate({})
        assert schema.objective == ""
        assert schema.steps  # repaired to non-empty
        assert isinstance(schema.measurements, list)
        assert isinstance(schema.risks, list)
        assert isinstance(schema.next_actions, list)


class TestTroubleshootingSchema:
    def test_full_valid_troubleshooting(self):
        data = {
            "symptom": "No laser output",
            "possible_causes": ["Misalignment", "Pump failure"],
            "diagnostic_checks": ["Check pump current", "Check alignment"],
            "recommended_actions": ["Realign cavity"],
            "expected_observations": ["Output resumes"],
            "safety_notes": ["Wear laser goggles"],
        }
        schema = TroubleshootingSchema.model_validate(data)
        assert schema.symptom == "No laser output"
        assert len(schema.possible_causes) == 2

    def test_empty_causes_gets_repaired(self):
        data = {"symptom": "Low power", "possible_causes": []}
        schema = TroubleshootingSchema.model_validate(data)
        assert len(schema.possible_causes) == 1
        assert "please review" in schema.possible_causes[0].lower()

    def test_missing_all_fields(self):
        schema = TroubleshootingSchema.model_validate({})
        assert schema.symptom == ""
        assert schema.possible_causes  # repaired


class TestExperimentReportSchema:
    def test_full_valid_report(self):
        data = {
            "title": "Nd:YAG CW Laser Characterization",
            "background": "Solid-state laser experiment",
            "method": "Measured output vs pump power",
            "observations": "Threshold at 1.2W pump",
            "data_summary": "Max output 450mW at 3W pump",
            "conclusion": "Slope efficiency 22%",
            "next_steps": ["Optimize OC reflectivity"],
        }
        schema = ExperimentReportSchema.model_validate(data)
        assert schema.title == "Nd:YAG CW Laser Characterization"

    def test_empty_title_gets_repaired(self):
        data = {"title": "", "background": "Some background"}
        schema = ExperimentReportSchema.model_validate(data)
        assert schema.title == "[Report title not provided]"

    def test_missing_title_gets_repaired(self):
        schema = ExperimentReportSchema.model_validate({})
        assert schema.title == "[Report title not provided]"


class TestValidateAndRepair:
    def test_plan_passes_with_full_data(self):
        data = {
            "objective": "Test",
            "setup": "Setup",
            "steps": ["Step 1"],
            "measurements": ["Power"],
            "risks": ["Eye hazard"],
            "next_actions": ["Next"],
        }
        result = validate_and_repair("plan", data)
        assert result.passed
        assert not result.repaired

    def test_plan_repairs_missing_steps(self):
        data = {"objective": "Test", "setup": "Setup"}
        result = validate_and_repair("plan", data)
        assert result.repaired
        assert "steps" in result.repaired_fields

    def test_troubleshooting_repairs_missing_causes(self):
        data = {"symptom": "No output"}
        result = validate_and_repair("troubleshooting", data)
        assert result.repaired

    def test_report_repairs_missing_title(self):
        data = {"background": "Some background"}
        result = validate_and_repair("report", data)
        assert result.repaired
        assert "title" in result.repaired_fields

    def test_unknown_content_type_returns_raw(self):
        data = {"foo": "bar"}
        result = validate_and_repair("unknown_type", data)
        assert result.validated == data

    def test_validation_result_to_dict(self):
        data = {"objective": "Test"}
        result = validate_and_repair("plan", data)
        d = result.to_dict()
        assert "content_type" in d
        assert "passed" in d
        assert "missing_fields" in d
        assert "repaired_fields" in d


class TestValidateArtifact:
    def test_returns_repaired_dict(self):
        data = {"symptom": "Low power"}
        repaired = validate_artifact("troubleshooting", data)
        assert isinstance(repaired, dict)
        assert "possible_causes" in repaired
        assert repaired["possible_causes"]  # non-empty after repair

