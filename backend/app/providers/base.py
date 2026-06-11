"""AI provider interface."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class AIProvider(ABC):
    """Abstract AI provider."""

    @abstractmethod
    async def generate_plan(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def generate_rezonator_schema(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
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
