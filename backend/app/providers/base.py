"""AI provider interface."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class AIProvider(ABC):
    """Abstract AI provider."""

    async def agent_turn(self, instructions: str, messages: list[dict], tools: list[dict]) -> dict:
        """One native tool-calling turn; orchestration belongs to the workbench."""
        raise NotImplementedError("当前模型适配器尚未提供 Agent 工具调用接口")

    async def extract_design_facts(self, context: dict, images: list[dict]) -> dict:
        """Extract quoted requirements; the deterministic solver owns the design."""
        raise NotImplementedError("当前模型适配器不支持设计需求提取")

    @abstractmethod
    async def generate_plan(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def generate_troubleshooting(self, symptoms: List[str], case_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def generate_report(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def generate_chat_response(self, context: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def analyze_image(self, image_data: bytes, mime_type: str, context: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def summarize_chat(
        self,
        messages: List[Dict[str, Any]],
        previous_summary: str | None = None,
    ) -> Dict[str, Any]:
        """Compress older messages into a rolling summary and extract durable memories.

        Returns a dict with keys:
          - summary (str): updated rolling summary
          - memories (list[dict]): each dict has keys content, memory_type, importance
        """
        pass
