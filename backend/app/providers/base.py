"""
AI提供者基类
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List


class AIProvider(ABC):
    """AI提供者抽象基类"""

    @abstractmethod
    async def generate_plan(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成实验计划

        Args:
            case_data: 实验案例数据

        Returns:
            包含计划内容的字典
        """
        pass

    @abstractmethod
    async def generate_rezonator_schema(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成ReZonator模式/模板草稿

        Args:
            case_data: 实验案例数据

        Returns:
            包含ReZonator模式的字典
        """
        pass

    @abstractmethod
    async def generate_troubleshooting(self, symptoms: List[str], case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成故障排查建议

        Args:
            symptoms: 症状列表
            case_data: 实验案例数据

        Returns:
            包含排查建议的字典
        """
        pass

    @abstractmethod
    async def generate_report(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成实验报告

        Args:
            case_data: 实验案例数据

        Returns:
            包含报告内容的字典
        """
        pass
