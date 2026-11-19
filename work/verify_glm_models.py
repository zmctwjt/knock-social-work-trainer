"""逐个验证用户限定的三个模型是否真的可用。

不经过系统，直接打智谱接口，避免把模型不可用的问题
误判成系统代码问题。逐个跑，分别报告状态码与响应摘要。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parent.parent / "deliverables" / "backend"
sys.path.insert(0, str(BACKEND))

# 从 .env 读密钥，不在这里硬编码
env = (BACKEND / ".env").read_text(encoding="utf-8")
KEY = ""
BASE = ""
for line in env.split("\n"):
    if line.startswith("GLM_API_KEY="):
        KEY = line.split("=", 1)[1].strip()
    elif line.startswith("GLM_BASE_URL="):
        BASE = line.split("=", 1)[1].strip()

MODELS = ["glm-4.7-flash", "glm-4-flash-250414", "glm-z1-flash"]


def main() -> int:
    if not KEY:
        print("GLM_API_KEY 为空，先写入 .env")
        return 1
    print(f"接口: {BASE}")
    print(f"密钥: {KEY[:6]}…{KEY[-4:]}")
    print()

    ok_models = []
    for model in MODELS:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是简洁的助手，只回答一个词。"},
                {"role": "user", "content": "用一个词形容雨天。"},
            ],
            "temperature": 0.3,
            "max_tokens": 32,
        }
        try:
            r = httpx.post(
                BASE,
                headers={"Authorization": f"Bearer {KEY}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            if r.status_code == 200:
                body = r.json()
                content = body["choices"][0]["message"]["content"]
                usage = body.get("usage", {})
                print(f"  ✅ {model:24s} 200  回复={content.strip()[:24]!r}  "
                      f"tokens={usage.get('total_tokens')}")
                ok_models.append(model)
            else:
                detail = r.text[:200].replace("\n", " ")
                print(f"  ❌ {model:24s} {r.status_code}  {detail}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ {model:24s} 异常: {type(exc).__name__}: {exc}")

    print()
    print(f"可用模型: {ok_models if ok_models else '无'}")
    if not ok_models:
        return 1
    if len(ok_models) < len(MODELS):
        print("⚠️ 部分模型不可用，需调整降级链")
    return 0


if __name__ == "__main__":
    sys.exit(main())
