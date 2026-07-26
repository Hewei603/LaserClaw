"""Deterministic mock AI provider for local and test use."""
from typing import Any, Dict, List

from .base import AIProvider

# Every mock artifact carries this marker so demo output can never be mistaken
# for a real model's analysis — the target user cannot tell them apart by tone.
DEMO_NOTICE = (
    "【演示模式】当前未接入真实 AI 模型,以下为固定模板内容,不针对你的具体案例。"
    "接入 DeepSeek/OpenAI 等模型的方法见《使用指南》第 1 节(docs/GUIDE_V2.md)。"
)


class MockProvider(AIProvider):
    """Template-based provider that requires no external model call."""

    async def generate_plan(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        cavity_type = case_data.get("cavity_type", "linear")
        goal = case_data.get("goal", "")
        steps = [
            "核对激光安全等级、护目镜、联锁、挡光板与准直时的功率上限。",
            "复核腔型几何、腔镜镀膜、增益介质、泵浦光路与预期稳定范围。",
            "先在低功率下对准泵浦与参考光路,再逐步提升泵浦功率。",
            "每次只调一个自由度,同步记录输出功率与模式形状。",
            "出现异常反射、热漂移或任何不安全迹象时立即停止并请人复核。",
        ]
        return {
            "notice": DEMO_NOTICE,
            "disclaimer": "仅为建议草稿,所有激光操作必须由具备资质的人员复核。",
            "title": f"{cavity_type} 腔实验计划(演示模板)",
            "goal": goal,
            "steps": [{"step": i + 1, "description": step, "estimated_time": "15-30 分钟"} for i, step in enumerate(steps)],
            "safety_notes": [
                "不得绕过联锁或实验室安全规程。",
                "全程佩戴对应波段护目镜并使用挡光板。",
                "高风险操作必须先经人工批准。",
            ],
            "required_equipment": self._equipment(cavity_type),
        }

    async def generate_troubleshooting(self, symptoms: List[str], case_data: Dict[str, Any]) -> Dict[str, Any]:
        if not symptoms:
            symptoms = ["一般性性能问题"]
        suggestions = []
        for symptom in symptoms:
            suggestions.append(
                {
                    "symptom": symptom,
                    "possible_causes": [
                        "泵浦功率低于阈值,或未有效耦合进增益介质。",
                        "腔镜偏出稳定对准范围。",
                        "热透镜或污染改变了模式匹配。",
                    ],
                    "solutions": [
                        "在安全低功率下确认泵浦到位,并与预期阈值对比。",
                        "检查腔镜指向、镀膜、洁净度与机械稳定性。",
                        "每次只改一个参数,记录结果后再继续。",
                    ],
                    "priority": "High" if "no output" in symptom.lower() or "无输出" in symptom else "Medium",
                }
            )
        return {
            "notice": DEMO_NOTICE,
            "disclaimer": "故障排查建议草稿,执行前需人工复核。",
            "summary": f"已为 {len(suggestions)} 个症状生成排查建议(演示模板)。",
            "suggestions": suggestions,
            "general_advice": [
                "保留书面对准记录。",
                "优先做可逆、低风险的检查,再考虑改动硬件。",
                "与设备手册或安全规程冲突时立即停止。",
            ],
        }

    async def generate_report(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "notice": DEMO_NOTICE,
            "disclaimer": "报告草稿:请填入实测数据并交由他人复核。",
            "title": case_data.get("title", "激光实验报告"),
            "date": "待填写",
            "sections": {
                "实验目的": case_data.get("goal", "待填写"),
                "装置": {
                    "cavity_type": case_data.get("cavity_type", "待填写"),
                    "parameters": case_data.get("parameters", {}),
                },
                "步骤": "见生成的实验计划与实验记录本。",
                "结果": {"输出功率": "待填写", "光束质量": "待填写", "稳定性": "待填写"},
                "问题与处理": {"观察到的症状": case_data.get("symptoms", []), "处理措施": "待填写"},
                "结论": "待填写",
                "改进建议": "待填写",
            },
            "attachments_note": "请附上原始测量数据、照片与腔型设计文件。",
        }

    async def generate_chat_response(self, context: Dict[str, Any]) -> Dict[str, Any]:
        case = context.get("case") or {}
        message = context.get("message", "")
        retrieved = context.get("retrieved_knowledge", [])
        title = case.get("title", "当前工作区")
        snippets = [item.get("snippet", "")[:180] for item in retrieved[:3] if item.get("snippet")]
        answer = (
            f"【演示模式】未接入真实 AI 模型,此回复为模板。当前案例:{title}。"
            f"你的消息:{message}。"
            "接入真实模型后,这里会基于案例上下文与引用来源给出针对性的建议。"
        )
        if snippets:
            answer += " 检索到的相关内容:" + " | ".join(snippets)
        return {
            "message": answer,
            "summary": "演示模式的案例感知回复。",
            "model_provider": "mock",
            "citations": context.get("citations", []),
        }

    async def analyze_image(self, image_data: bytes, mime_type: str, context: Dict[str, Any]) -> Dict[str, Any]:
        filename = context.get("filename", "上传的图片")
        case_title = context.get("case", {}).get("title", "案例")
        return {
            "notice": DEMO_NOTICE,
            "disclaimer": "演示模式的图像分析占位结果;正式分析需接入具备视觉能力的模型。",
            "title": f"图像分析:{filename}",
            "case_title": case_title,
            "image_type_hypothesis": "激光装置照片、仿真示意图或光斑图",
            "observations": [
                "图片已接收并挂到案例名下。",
                "正式分析会识别光学元件、光路、标注与可见的风险点。",
                "任何由图片推断的几何或光斑质量,使用前都应与实测数据对比。",
            ],
            "recommended_follow_up": [
                "如有条件,补充波长、功率、曝光设置与相机标尺。",
                "查看图像分析后,可让 Agent 生成故障排查或实验报告。",
            ],
            "confidence": "mock",
            "input_bytes": len(image_data),
            "mime_type": mime_type,
        }

    def _equipment(self, cavity_type: str) -> List[str]:
        base = ["激光护目镜", "光学平台", "挡光板", "功率计", "对准卡片"]
        specific = {
            "linear": ["输入镜", "输出耦合镜", "增益介质"],
            "ring": ["四片腔镜", "光隔离器", "增益介质"],
            "bow-tie": ["四片腔镜", "增益介质"],
            "custom": ["经验证的光学元件"],
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
