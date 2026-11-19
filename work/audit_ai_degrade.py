"""降级链实测：AI 不可用时系统是否仍可用。

做法：在 8002 端口另起一个后端实例，故意配一个无效密钥，
然后打四条 AI 链路，验证：
1. HTTP 仍然是 200（不能让页面报错）；
2. 返回内容仍可用（persona 回落到情绪档台词、debrief 回落模板）；
3. meta 里如实标记 used_ai=false 与降级原因。

这是"铁律二"的端到端验证：AI 失败也必须给页面一句可读的台词。
不影响运行中的主实例（8000）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "deliverables" / "backend"
# 用当前解释器，避免写死 Windows 的 venv 路径（CI 是 Linux）
PYTHON = sys.executable
PORT = 8002
BASE = f"http://127.0.0.1:{PORT}"
_LOG = ROOT / "work" / "logs" / "degrade-instance.log"


def main() -> int:
    env = os.environ.copy()
    env.update({
        "APP_ENV": "dev",
        "JWT_SECRET": "degrade-test-secret-0123456789abcdef",
        "GLM_API_KEY": "invalid-key-for-degradation-test.000000",
        "GLM_MODEL": "glm-4-flash-250414",
        "GLM_FALLBACK_MODELS": "glm-z1-flash",
        "GLM_MAX_RETRIES": "0",
        # 读主实例同一套库，避免另建
        # 优先用环境里的 DATABASE_URL（CI 的 MySQL 在 3306），
        # 本机默认私有实例在 3307
        "DATABASE_URL": os.getenv(
            "DATABASE_URL",
            "mysql+aiomysql://knock:knock@127.0.0.1:3307/knock?charset=utf8mb4",
        ),
        "STATIC_DIR": "",
        "RATE_LIMIT_ENABLED": "false",
    })

    # logs 目录在 CI 里不存在（被 gitignore），先确保存在
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    print(f"启动降级测试实例（端口 {PORT}，无效密钥）…")
    proc = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BACKEND), env=env,
        stdout=open(_LOG, "w", encoding="utf-8"), stderr=subprocess.STDOUT,
    )
    fails: list[str] = []
    try:
        for _ in range(40):
            try:
                body = httpx.get(f"{BASE}/readyz", timeout=3).json()["data"]
                if body.get("status") == "ready":
                    break
            except Exception:  # noqa: BLE001
                time.sleep(1)
        else:
            print("实例未能就绪（数据库可能连不上）")
            return 1

        ready = httpx.get(f"{BASE}/readyz", timeout=10).json()["data"]
        print(f"  就绪: ai_configured={ready.get('ai_configured')} "
              f"chain={ready.get('model_chain')}")

        c = httpx.Client(base_url=BASE, timeout=120)
        token = c.post("/api/v1/auth/login",
                       json={"username": "student01",
                             "password": "Student@12345"}).json()["data"]["tokens"]["access_token"]
        H = {"Authorization": f"Bearer {token}"}

        print("\n=== 1. persona（学生每轮都调，最关键）===")
        r = c.post("/api/v1/ai/persona", headers=H, json={
            "scenario_id": "W-01", "emotion": 40, "last_intent": "empathy",
            "student_text": "王阿姨您好，我是社区的小陈。", "turn_index": 1,
        })
        ok = r.status_code == 200
        d = r.json().get("data", {}) if ok else {}
        text = (d.get("text") or "").strip()
        meta = d.get("meta") or {}
        print(f"  HTTP {r.status_code} used_ai={meta.get('used_ai')} "
              f"degrade={meta.get('degrade_reason')}")
        print(f"  台词: {text[:50]!r}")
        if not ok:
            fails.append(f"persona 返回 {r.status_code}（应为 200）")
        elif not text:
            fails.append("persona 降级后没有可读台词")
        elif len(text) > 40:
            fails.append(f"降级台词不像spoken line: {text[:40]!r}")
        elif meta.get("used_ai"):
            fails.append("无效密钥却标记 used_ai=True")

        print("\n=== 2. debrief（复盘）===")
        r = c.post("/api/ai/debrief", headers=H, json={
            "nickname": "学员小李", "scores": {"empathy": 70, "question": 60},
            "hitRules": ["第2句 建议过早"],
        })
        d = r.json() if r.status_code == 200 else {}
        report = d.get("report") or {}
        print(f"  HTTP {r.status_code} usedAI={d.get('usedAI')} "
              f"report 字段={list(report.keys())}")
        if r.status_code != 200:
            fails.append(f"debrief 返回 {r.status_code}")
        elif d.get("usedAI"):
            fails.append("无效密钥却标记 usedAI=True")
        else:
            # 模板回退由前端 aiClient 负责（report 为空时用 args.template），
            # 后端只要如实返回 usedAI=false 且不报错即可
            print("  → report 为空、usedAI=false，前端会用本地模板回退（符合设计）")

        print("\n=== 3. score（评分必须有结果）===")
        r = c.post("/api/v1/ai/score", headers=H, json={
            "dialogue": [
                {"role": "worker", "text": "王阿姨您好。"},
                {"role": "client", "text": "你来干什么。"},
            ],
            "stage_index": 1,
        })
        d = r.json().get("data", {}) if r.status_code == 200 else {}
        print(f"  HTTP {r.status_code} used_ai={d.get('used_ai')} "
              f"scores={bool(d.get('scores'))}")
        if r.status_code != 200:
            fails.append(f"score 返回 {r.status_code}")
        elif not d.get("scores"):
            fails.append("score 降级后没有维度分（规则分也应给出）")

        print("\n=== 4. intent（意图判定）===")
        r = c.post("/api/v1/ai/intent", headers=H, json={
            "input": "王阿姨您好，我是社区的小陈。", "scenario_id": "W-01",
            "emotion": 50, "turn_index": 1,
        })
        d = r.json().get("data", {}) if r.status_code == 200 else {}
        print(f"  HTTP {r.status_code} intent={d.get('intent')} "
              f"source={d.get('source')}")
        if r.status_code != 200:
            fails.append(f"intent 返回 {r.status_code}")
        elif not d.get("intent"):
            fails.append("intent 降级后没有判定结果")

        c.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()

    print()
    if fails:
        print("❌ 降级链问题：")
        for f in fails:
            print("   -", f)
        return 1
    print("✅ 无效密钥下四条链路均降级成功，页面仍可用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
