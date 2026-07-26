"""Simple deterministic Agent planner."""
from __future__ import annotations

# Step titles are user-facing: they appear in the Agent task timeline.
MODE_LABELS = {
    "plan": "实验计划",
    "troubleshooting": "故障排查",
    "report": "实验报告",
    "chat": "对话",
    "stability": "稳定性分析",
    "beam_profile": "光斑分析",
    "spectrum": "光谱分析",
    "components": "元件清单",
    "module_management": "模块管理",
    "cavity_design": "谐振腔设计",
    "phase_match": "相位匹配",
    "coating_tmm": "镀膜评估",
    "component_match": "元件匹配",
    "power_curve": "功率曲线",
}


def mode_label(mode: str) -> str:
    """Chinese display name for an Agent mode (falls back to the raw name)."""
    return MODE_LABELS.get(mode, mode)


def build_plan(mode: str) -> list[dict[str, str]]:
    """Return a minimal multi-step plan for the requested Agent mode."""
    if mode in {"stability", "beam_profile", "spectrum", "components", "module_management",
                "cavity_design", "phase_match", "coating_tmm", "component_match", "power_curve"}:
        return [
            {
                "title": "读取案例与模块上下文",
                "rationale": "Agent 需要先了解当前案例和已有模块。",
            },
            {
                "title": "检查模块输入",
                "rationale": "模块工作流依赖已上传的文件、参数与既有生成内容。",
            },
            {
                "title": f"运行「{mode_label(mode)}」模块",
                "rationale": "通过可审计的工具创建或更新所请求的案例模块。",
            },
            {
                "title": "保存模块结果与审计记录",
                "rationale": "持久化模块输出、生成内容与工具调用,供复核。",
            },
        ]
    return [
        {
            "title": "读取案例上下文",
            "rationale": "Agent 的工作必须基于所选实验案例。",
        },
        {
            "title": "检索相关知识",
            "rationale": "历史案例、附件与既有生成内容提供证据。",
        },
        {
            "title": f"生成「{mode_label(mode)}」草稿",
            "rationale": "基于案例与检索证据产出结构化内容。",
        },
        {
            "title": "保存内容与审计记录",
            "rationale": "持久化输出、步骤与工具调用,供复核。",
        },
    ]
