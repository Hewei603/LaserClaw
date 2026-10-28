"""Live subscription acceptance using a disposable database, never lab cases.

Run from backend/: .venv/Scripts/python scripts/validate_codex_exec_live.py
Uses the signed-in account's Codex allowance for a connection, image, and tool-loop test.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from datetime import datetime, timezone
import zlib


def blue_png():
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))

    header = struct.pack(">2I5B", 200, 200, 8, 2, 0, 0, 0)
    pixels = b"".join(b"\0" + bytes([0, 80, 255]) * 200 for _ in range(200))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


def main():
    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    with tempfile.TemporaryDirectory(prefix="laserclaw-codex-acceptance-") as directory:
        root = Path(directory)
        os.environ.update(
            LASERCLAW_NO_DOTENV="1", DATABASE_URL="sqlite:///" + (root / "test.db").as_posix(),
            AGENT_SETTINGS_FILE=str(root / "settings.json"), UPLOAD_DIR=str(root / "uploads"),
            VECTOR_STORE_DIR=str(root / "vectors"), AI_PROVIDER="codex_exec", REQUIRE_AUTH="false",
            EMBEDDING_PROVIDER="local", LITERATURE_PROVIDERS="mock",
        )
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from app.database import Base, engine
        # The production startup migrates old data by design. Acceptance must
        # neither copy nor repair the user's lab database and attachments.
        with patch("app.data_migration.migrate_legacy_data", return_value=[]):
            from app.main import app
        from app.providers.codex_exec import CodexExecProvider, codex_status
        import asyncio

        evidence = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "runtime": codex_status(refresh=True)}
        assert evidence["runtime"]["ready"], evidence["runtime"]
        Base.metadata.create_all(engine)
        try:
            with TestClient(app) as client:
                configuration = client.put("/api/settings/agent", json={
                    "provider": "codex_exec", "model": "gpt-6.1-sol",
                })
                assert configuration.status_code == 200, configuration.text
                test = client.post("/api/settings/agent/codex/test", json={
                    "provider": "codex_exec", "model": "gpt-6.1-sol",
                })
                assert test.status_code == 200, test.text
                evidence["connection"] = test.json()
                print("Connection: passed", flush=True)
                picture = asyncio.run(CodexExecProvider().analyze_image(
                    blue_png(), "image/png",
                    {"message": "这是一张纯蓝色测试图片，只描述实际看到的内容，不推测实验。"},
                ))
                assert picture.get("observations"), picture
                evidence["image"] = picture
                print("Image input: passed", flush=True)
                response = client.post("/api/cases", json={"title": "Codex订阅隔离验收", "description": "临时测试，不是实验记录"})
                assert response.status_code == 201, response.text
                case_id = response.json()["id"]
                request = client.post(f"/api/cases/{case_id}/workbench/runs", json={"message":
                    "这是一项完整且信息充分的接口验收：用 analyze_optical_system 计算1064nm驻波腔，"
                    "M1为平面镜，中间50mm空气，M2为凹面R100mm，正入射。"
                    "只需这一次计算，再调用finish，给出稳定性和M1处基模半径，引用真实计算的工具记录ID。"
                    "不需要查库存、查文献、保存光学工程或提问。"})
                assert request.status_code == 202, request.text
                run = client.get(f"/api/cases/{case_id}/workbench/runs/{request.json()['task_id']}").json()
                assert run["status"] == "completed", run
                optical = [t for t in run["tools"] if t["name"] == "analyze_optical_system" and t["status"] == "completed"]
                assert optical and optical[0]["output"]["stable_both_planes"], run
                assert optical[0]["id"] in run["result"]["evidence_tool_call_ids"], run
                evidence["workbench"] = run
                print("Agent -> actual physics -> finish -> persisted evidence: passed", flush=True)
                artifact = client.post(f"/api/cases/{case_id}/generate-report", json={"use_rag": False})
                assert artifact.status_code == 200, artifact.text
                evidence["report"] = artifact.json()
                print("Report generation: passed", flush=True)
            destination = backend.parent / "output/validation/codex-exec-live.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            print(str(destination), flush=True)
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
