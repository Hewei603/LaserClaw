"""
数据库种子数据脚本
用于创建演示案例
"""
import asyncio
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app.models import ExperimentCase, GeneratedContent
from app.providers import get_ai_provider


# 示例案例数据
SAMPLE_CASES = [
    {
        "title": "Ti:Sapphire环形腔激光器对准",
        "description": "钛宝石激光器环形腔的初次搭建和对准实验",
        "cavity_type": "ring",
        "goal": "搭建稳定的Ti:Sapphire环形腔激光器，实现连续波输出，输出功率>500mW",
        "parameters": {
            "波长": "800nm",
            "泵浦功率": "5W",
            "晶体类型": "Ti:Sapphire",
            "晶体长度": "10mm",
            "腔长": "1.5m"
        },
        "symptoms": []
    },
    {
        "title": "Nd:YAG线性腔热效应问题排查",
        "description": "Nd:YAG激光器出现严重热效应，需要排查和解决",
        "cavity_type": "linear",
        "goal": "解决Nd:YAG激光器的热效应问题，恢复稳定输出",
        "parameters": {
            "波长": "1064nm",
            "泵浦功率": "10W",
            "晶体类型": "Nd:YAG",
            "晶体长度": "5mm",
            "腔长": "50cm",
            "输出镜透射率": "10%"
        },
        "symptoms": ["热效应", "输出不稳定", "模式跳变"]
    },
    {
        "title": "OPO蝴蝶形腔参数优化",
        "description": "光参量振荡器蝴蝶形腔的参数优化实验",
        "cavity_type": "bow-tie",
        "goal": "优化OPO蝴蝶形腔参数，提高转换效率和输出稳定性",
        "parameters": {
            "泵浦波长": "532nm",
            "信号波长": "1064nm",
            "闲频波长": "1550nm",
            "非线性晶体": "PPLN",
            "晶体长度": "20mm",
            "腔长": "80cm"
        },
        "symptoms": ["输出不稳定"]
    },
    {
        "title": "光纤激光器系统调试",
        "description": "新搭建的光纤激光器系统初次调试",
        "cavity_type": "custom",
        "goal": "完成光纤激光器系统的初次调试，实现稳定的脉冲输出",
        "parameters": {
            "波长": "1550nm",
            "增益光纤": "Er-doped fiber",
            "光纤长度": "5m",
            "重复频率": "10MHz",
            "脉冲宽度": "100ps"
        },
        "symptoms": ["无输出"]
    },
    {
        "title": "锁模激光器稳定性测试",
        "description": "锁模激光器的长期稳定性测试和优化",
        "cavity_type": "linear",
        "goal": "测试并优化锁模激光器的长期稳定性，确保连续运行24小时以上",
        "parameters": {
            "波长": "1030nm",
            "重复频率": "80MHz",
            "脉冲宽度": "200fs",
            "平均功率": "2W",
            "锁模方式": "被动锁模"
        },
        "symptoms": ["对准漂移", "模式跳变"]
    }
]


async def generate_content_for_case(db: Session, case: ExperimentCase):
    """为案例生成所有类型的内容"""
    provider = get_ai_provider()

    case_data = {
        "title": case.title,
        "description": case.description,
        "cavity_type": case.cavity_type,
        "goal": case.goal,
        "parameters": case.parameters,
        "symptoms": case.symptoms
    }

    # 生成实验计划
    plan_content = await provider.generate_plan(case_data)
    plan = GeneratedContent(
        case_id=case.id,
        content_type="plan",
        content=plan_content
    )
    db.add(plan)

    # 生成ReZonator模式
    rezonator_content = await provider.generate_rezonator_schema(case_data)
    rezonator = GeneratedContent(
        case_id=case.id,
        content_type="rezonator",
        content=rezonator_content
    )
    db.add(rezonator)

    # 如果有症状，生成故障排查
    if case.symptoms:
        troubleshooting_content = await provider.generate_troubleshooting(
            case.symptoms, case_data
        )
        troubleshooting = GeneratedContent(
            case_id=case.id,
            content_type="troubleshooting",
            content=troubleshooting_content
        )
        db.add(troubleshooting)

    # 生成实验报告
    report_content = await provider.generate_report(case_data)
    report = GeneratedContent(
        case_id=case.id,
        content_type="report",
        content=report_content
    )
    db.add(report)

    db.commit()


async def seed_database():
    """填充数据库"""
    print("开始填充数据库...")

    # 创建所有表
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 检查是否已有数据
        existing_count = db.query(ExperimentCase).count()
        if existing_count > 0:
            print(f"数据库已有 {existing_count} 个案例，跳过填充")
            return

        # 创建示例案例
        for case_data in SAMPLE_CASES:
            print(f"创建案例: {case_data['title']}")
            case = ExperimentCase(**case_data)
            db.add(case)
            db.commit()
            db.refresh(case)

            # 为案例生成内容
            print(f"  生成内容...")
            await generate_content_for_case(db, case)

        print(f"成功创建 {len(SAMPLE_CASES)} 个示例案例")

    except Exception as e:
        print(f"填充数据库时出错: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(seed_database())
