"""
模拟AI提供者（用于演示模式）
"""
from typing import Dict, Any, List
from .base import AIProvider


class MockProvider(AIProvider):
    """模拟AI提供者，使用规则和模板生成内容"""

    async def generate_plan(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成实验计划（基于模板）"""
        cavity_type = case_data.get("cavity_type", "linear")
        goal = case_data.get("goal", "")

        # 基于腔型的基础步骤
        base_steps = {
            "linear": [
                "准备线性腔所需的平面镜和凹面镜",
                "设置激光晶体位置，确保泵浦光聚焦到晶体中心",
                "粗调输出镜和高反镜的位置，使腔长符合设计值",
                "使用可见光辅助对准，确保光路共线",
                "精调镜片角度，观察输出功率变化",
                "优化腔长和镜片位置，达到最佳输出"
            ],
            "ring": [
                "准备环形腔所需的四面镜片",
                "按照设计角度放置各镜片，形成闭合光路",
                "设置激光晶体和泵浦系统",
                "使用可见光辅助对准，确保光路形成完整环路",
                "逐个精调镜片角度，优化模式质量",
                "检查单向运转特性，调整隔离器位置"
            ],
            "bow-tie": [
                "准备蝴蝶形腔所需的四面镜片",
                "按照蝴蝶形几何结构放置镜片",
                "设置激光晶体在腔内合适位置",
                "使用可见光辅助对准，确保光路闭合",
                "精调各镜片角度，优化腔内模式",
                "测试腔的稳定性和输出特性"
            ],
            "custom": [
                "根据设计方案准备所需光学元件",
                "按照设计参数搭建腔体结构",
                "设置激光增益介质和泵浦系统",
                "进行初步光路对准",
                "逐步精调各元件位置和角度",
                "测试并优化系统性能"
            ]
        }

        steps = base_steps.get(cavity_type, base_steps["custom"])

        return {
            "disclaimer": "⚠️ 这是启发式建议，需要人工验证",
            "title": f"{cavity_type}腔实验计划",
            "goal": goal,
            "steps": [
                {"step": i+1, "description": step, "estimated_time": "15-30分钟"}
                for i, step in enumerate(steps)
            ],
            "safety_notes": [
                "佩戴激光防护眼镜",
                "确保激光功率在安全范围内",
                "避免直视激光束或反射光",
                "保持工作区域整洁，避免杂散反射"
            ],
            "required_equipment": self._get_equipment_list(cavity_type)
        }

    async def generate_rezonator_schema(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成ReZonator模式草稿"""
        cavity_type = case_data.get("cavity_type", "linear")
        parameters = case_data.get("parameters", {})

        # 基础模板
        schema = {
            "disclaimer": "⚠️ 这是模板草稿，需要根据实际参数调整",
            "cavity_type": cavity_type,
            "elements": [],
            "notes": "此模式需要在ReZonator中进一步编辑和验证"
        }

        # 根据腔型生成元件列表
        if cavity_type == "linear":
            schema["elements"] = [
                {"type": "mirror", "name": "M1", "ROC": "平面", "position": 0},
                {"type": "crystal", "name": "Crystal", "length": parameters.get("crystal_length", "10mm"), "position": 50},
                {"type": "mirror", "name": "M2", "ROC": parameters.get("output_mirror_roc", "100mm"), "position": 100}
            ]
        elif cavity_type == "ring":
            schema["elements"] = [
                {"type": "mirror", "name": "M1", "angle": "45°", "position": 0},
                {"type": "mirror", "name": "M2", "angle": "45°", "position": 100},
                {"type": "crystal", "name": "Crystal", "position": 150},
                {"type": "mirror", "name": "M3", "angle": "45°", "position": 200},
                {"type": "mirror", "name": "M4", "angle": "45°", "position": 250}
            ]
        elif cavity_type == "bow-tie":
            schema["elements"] = [
                {"type": "mirror", "name": "M1", "position": 0},
                {"type": "mirror", "name": "M2", "position": 100},
                {"type": "crystal", "name": "Crystal", "position": 150},
                {"type": "mirror", "name": "M3", "position": 200},
                {"type": "mirror", "name": "M4", "position": 250}
            ]

        return schema

    async def generate_troubleshooting(self, symptoms: List[str], case_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成故障排查建议"""
        # 症状到解决方案的映射
        symptom_solutions = {
            "无输出": [
                "检查泵浦光是否正常到达晶体",
                "验证腔镜对准是否正确",
                "确认泵浦功率是否超过阈值",
                "检查输出镜透射率是否合适"
            ],
            "输出不稳定": [
                "检查机械稳定性，加固光学平台",
                "检查温度控制系统是否正常",
                "验证泵浦源稳定性",
                "检查是否存在气流扰动"
            ],
            "模式跳变": [
                "优化腔长，避免模式简并",
                "改善泵浦光模式匹配",
                "检查热透镜效应补偿",
                "考虑添加光阑限制横模"
            ],
            "热效应": [
                "改善晶体冷却系统",
                "降低泵浦功率或使用脉冲泵浦",
                "优化泵浦光聚焦位置",
                "考虑使用热导率更好的晶体"
            ],
            "对准漂移": [
                "检查并加固所有机械连接",
                "改善温度稳定性",
                "使用更稳定的镜架",
                "考虑主动稳定系统"
            ]
        }

        suggestions = []
        for symptom in symptoms:
            if symptom in symptom_solutions:
                suggestions.append({
                    "symptom": symptom,
                    "possible_causes": self._get_possible_causes(symptom),
                    "solutions": symptom_solutions[symptom],
                    "priority": "高" if symptom in ["无输出", "输出不稳定"] else "中"
                })

        return {
            "disclaimer": "⚠️ 这是启发式建议，实际问题可能更复杂",
            "summary": f"检测到 {len(symptoms)} 个症状",
            "suggestions": suggestions,
            "general_advice": [
                "按优先级逐个排查问题",
                "每次只改变一个参数，观察效果",
                "记录所有调整和观察结果",
                "必要时寻求有经验人员的帮助"
            ]
        }

    async def generate_report(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成实验报告"""
        return {
            "disclaimer": "⚠️ 这是自动生成的报告模板，需要补充实际数据",
            "title": case_data.get("title", "激光实验报告"),
            "date": "待填写",
            "sections": {
                "实验目的": case_data.get("goal", "待填写"),
                "实验装置": {
                    "腔型": case_data.get("cavity_type", "待填写"),
                    "主要参数": case_data.get("parameters", {})
                },
                "实验步骤": "参考生成的实验计划",
                "实验结果": {
                    "输出功率": "待测量",
                    "光束质量": "待测量",
                    "稳定性": "待评估"
                },
                "问题与解决": {
                    "遇到的问题": case_data.get("symptoms", []),
                    "解决方法": "参考故障排查建议"
                },
                "结论": "待总结",
                "改进建议": "待补充"
            },
            "attachments_note": "请上传相关图片、数据文件和ReZonator模式文件"
        }

    def _get_equipment_list(self, cavity_type: str) -> List[str]:
        """获取所需设备列表"""
        base_equipment = [
            "激光防护眼镜",
            "光学平台",
            "镜架和调整架",
            "功率计",
            "光束分析仪"
        ]

        cavity_specific = {
            "linear": ["平面镜", "凹面镜", "激光晶体"],
            "ring": ["四面反射镜", "激光晶体", "光隔离器"],
            "bow-tie": ["四面反射镜", "激光晶体"],
            "custom": ["根据设计选择光学元件"]
        }

        return base_equipment + cavity_specific.get(cavity_type, [])

    def _get_possible_causes(self, symptom: str) -> List[str]:
        """获取可能的原因"""
        causes = {
            "无输出": ["泵浦功率不足", "腔镜未对准", "损耗过大"],
            "输出不稳定": ["机械振动", "温度波动", "泵浦不稳定"],
            "模式跳变": ["腔长不稳定", "热透镜效应", "泵浦模式不匹配"],
            "热效应": ["冷却不足", "泵浦功率过高", "晶体吸收过大"],
            "对准漂移": ["热膨胀", "机械松动", "环境温度变化"]
        }
        return causes.get(symptom, ["原因待分析"])
