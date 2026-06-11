"""Deterministic mock AI provider for local and test use."""
from typing import Any, Dict, List

from .base import AIProvider


class MockProvider(AIProvider):
    """Template-based provider that requires no external model call."""

    async def generate_plan(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        cavity_type = case_data.get("cavity_type", "linear")
        goal = case_data.get("goal", "")
        steps = [
            "Verify laser class controls, PPE, interlocks, beam dumps, and alignment power limits.",
            "Review the cavity geometry, mirror coatings, gain medium, pump path, and expected stability range.",
            "Align the pump beam and low-power reference path before raising pump power.",
            "Tune mirrors one degree of freedom at a time while recording output power and mode shape.",
            "Stop and request human review if unexpected reflections, thermal drift, or unsafe conditions appear.",
        ]
        return {
            "disclaimer": "Advisory draft only. A qualified human must review all laser operations.",
            "title": f"{cavity_type} cavity experiment plan",
            "goal": goal,
            "steps": [{"step": i + 1, "description": step, "estimated_time": "15-30 min"} for i, step in enumerate(steps)],
            "safety_notes": [
                "Do not bypass interlocks or local SOPs.",
                "Use proper laser eyewear and beam blocks.",
                "Keep high-risk actions behind human approval.",
            ],
            "required_equipment": self._equipment(cavity_type),
        }

    async def generate_rezonator_schema(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        cavity_type = case_data.get("cavity_type", "linear")
        parameters = case_data.get("parameters", {})
        return {
            "disclaimer": "Draft schema only. Validate dimensions and stability in ReZonator before use.",
            "cavity_type": cavity_type,
            "elements": [
                {"type": "mirror", "name": "M1", "position": 0, "roc": parameters.get("m1_roc", "flat")},
                {"type": "crystal", "name": "Gain medium", "position": 50, "length": parameters.get("crystal_length", "10 mm")},
                {"type": "mirror", "name": "M2", "position": 100, "roc": parameters.get("m2_roc", "100 mm")},
            ],
            "notes": "Replace placeholder positions with measured geometry and verify safety margins.",
        }

    async def generate_troubleshooting(self, symptoms: List[str], case_data: Dict[str, Any]) -> Dict[str, Any]:
        if not symptoms:
            symptoms = ["general performance issue"]
        suggestions = []
        for symptom in symptoms:
            suggestions.append(
                {
                    "symptom": symptom,
                    "possible_causes": [
                        "Pump power below threshold or poorly coupled into the gain medium.",
                        "Cavity mirrors are outside the stable alignment range.",
                        "Thermal lensing or contamination changed the mode match.",
                    ],
                    "solutions": [
                        "Confirm pump delivery at low safe power and compare against the expected threshold.",
                        "Inspect mirror orientation, coating, cleanliness, and mechanical stability.",
                        "Change one parameter at a time and record the result before proceeding.",
                    ],
                    "priority": "High" if "no output" in symptom.lower() or "无输出" in symptom else "Medium",
                }
            )
        return {
            "disclaimer": "Advisory troubleshooting draft. Human review is required before applying changes.",
            "summary": f"Prepared troubleshooting guidance for {len(suggestions)} symptom(s).",
            "suggestions": suggestions,
            "general_advice": [
                "Preserve a written alignment log.",
                "Prefer reversible, low-risk checks before changing hardware.",
                "Stop if the result conflicts with the device manual or safety procedure.",
            ],
        }

    async def generate_report(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "disclaimer": "Draft report. Fill in measured values and have the report reviewed.",
            "title": case_data.get("title", "Laser experiment report"),
            "date": "pending",
            "sections": {
                "Purpose": case_data.get("goal", "pending"),
                "Setup": {
                    "cavity_type": case_data.get("cavity_type", "pending"),
                    "parameters": case_data.get("parameters", {}),
                },
                "Procedure": "See generated plan and lab notebook.",
                "Results": {"output_power": "pending", "beam_quality": "pending", "stability": "pending"},
                "Problems and Solutions": {"observed_symptoms": case_data.get("symptoms", []), "actions": "pending"},
                "Conclusion": "pending",
                "Improvement Suggestions": "pending",
            },
            "attachments_note": "Attach raw measurements, photos, and ReZonator files.",
        }

    async def generate_chat_response(self, context: Dict[str, Any]) -> Dict[str, Any]:
        case = context.get("case") or {}
        message = context.get("message", "")
        retrieved = context.get("retrieved_knowledge", [])
        title = case.get("title", "the selected workspace")
        snippets = [item.get("snippet", "")[:180] for item in retrieved[:3] if item.get("snippet")]
        answer = (
            f"I am using the current case context for {title}. "
            f"Your message was: {message}. "
            "Based on the indexed context, I would keep the discussion advisory, verify safety assumptions, "
            "and use the cited sources before changing the experiment."
        )
        if snippets:
            answer += " Relevant retrieved context: " + " | ".join(snippets)
        return {
            "message": answer,
            "summary": "Mock case-aware chat response.",
            "model_provider": "mock",
            "citations": context.get("citations", []),
        }

    async def analyze_image(self, image_data: bytes, mime_type: str, context: Dict[str, Any]) -> Dict[str, Any]:
        filename = context.get("filename", "uploaded image")
        case_title = context.get("case", {}).get("title", "case")
        return {
            "disclaimer": "Mock visual analysis for local development. Use a configured vision model for production review.",
            "title": f"Image analysis for {filename}",
            "case_title": case_title,
            "image_type_hypothesis": "laser setup, simulation drawing, or beam profile",
            "observations": [
                "Image file was accepted and attached to the case.",
                "Production analysis should identify optical components, beam path, annotations, and visible risk indicators.",
                "Compare any inferred geometry or spot quality against measured data before acting on it.",
            ],
            "recommended_follow_up": [
                "Add wavelength, power, exposure settings, and camera scale if available.",
                "Ask the Agent to generate troubleshooting or a report after reviewing the image analysis.",
            ],
            "confidence": "mock",
            "input_bytes": len(image_data),
            "mime_type": mime_type,
        }

    def _equipment(self, cavity_type: str) -> List[str]:
        base = ["laser eyewear", "optical table", "beam blocks", "power meter", "alignment card"]
        specific = {
            "linear": ["input mirror", "output coupler", "gain medium"],
            "ring": ["four mirrors", "isolator", "gain medium"],
            "bow-tie": ["four mirrors", "gain medium"],
            "custom": ["validated optical elements"],
        }
        return base + specific.get(cavity_type, specific["custom"])

    async def summarize_chat(
        self,
        messages: List[Dict[str, Any]],
        previous_summary: str | None = None,
    ) -> Dict[str, Any]:
        joined = " ".join(item.get("content", "") for item in messages)
        base = (previous_summary + " " if previous_summary else "")
        summary = (base + joined)[:1200]

        memories: List[Dict[str, Any]] = []
        lower = joined.lower()
        if "no output" in lower or "不出光" in lower or "无输出" in lower:
            memories.append({
                "memory_type": "fact",
                "content": "The user reported a no-output laser cavity issue.",
                "importance": 3,
            })
        if "alignment" in lower or "准直" in lower:
            memories.append({
                "memory_type": "fact",
                "content": "Alignment was discussed during this session.",
                "importance": 2,
            })
        if "safety" in lower or "安全" in lower or "ppe" in lower:
            memories.append({
                "memory_type": "constraint",
                "content": "Safety requirements or PPE were mentioned.",
                "importance": 2,
            })
        return {"summary": summary, "memories": memories}
