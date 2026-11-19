"""三个允许模型的实际延迟对比。

背景：接入真实密钥后发现冷调用 27–39 秒，persona 已接近 45s 超时。
主模型 glm-4.7-flash 是推理模型，即使关掉 thinking 也慢。
用户限定只能用这三个模型，但**顺序由我们决定**——所以要实测谁快。

测法：用一段接近真实 persona 的提示词，每个模型各跑 3 次取中位数，
避免单次抖动误导结论。
"""
from __future__ import annotations

import statistics
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parent.parent / "deliverables" / "backend"
env = (BACKEND / ".env").read_text(encoding="utf-8")
KEY = BASE = ""
for line in env.split("\n"):
    if line.startswith("GLM_API_KEY="):
        KEY = line.split("=", 1)[1].strip()
    elif line.startswith("GLM_BASE_URL="):
        BASE = line.split("=", 1)[1].strip()

MODELS = ["glm-4.7-flash", "glm-4-flash-250414", "glm-z1-flash"]

SYSTEM = (
    "你在扮演一位 68 岁的空巢老人王阿姨。老伴去世三年，独子在广州工作。\n"
    "说话风格：短句、口语、偶尔停顿，不主动示弱，也不过度倾诉。\n"
    "禁止：说教、安慰式套话、总结对方的话。\n"
    "只输出角色的一句话回应，不要任何解释或格式标记。"
)
USER = (
    "社工：王阿姨您好，我是社区的小陈，今天想陪您聊聊最近的情况。\n"
    "情绪值 42/100（偏低）。请以王阿姨身份回应一句。"
)


def main() -> int:
    print(f"{'模型':<22}{'中位数':>10}{'最快':>9}{'最慢':>9}  备注")
    print("-" * 70)
    summary = []
    for model in MODELS:
        samples: list[int] = []
        note = ""
        for _ in range(3):
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": USER},
                ],
                "max_tokens": 120,
                "temperature": 0.3,
                "thinking": {"type": "disabled"},
            }
            t0 = time.perf_counter()
            try:
                r = httpx.post(
                    BASE,
                    headers={"Authorization": f"Bearer {KEY}"},
                    json=payload,
                    timeout=90,
                )
                ms = round((time.perf_counter() - t0) * 1000)
                if r.status_code != 200:
                    note = f"HTTP {r.status_code}"
                    continue
                body = r.json()
                msg = body["choices"][0]["message"]
                content = (msg.get("content") or "").strip()
                if "<think" in content.lower():
                    note = "含思维链标签"
                elif not content:
                    note = "正文为空"
                samples.append(ms)
            except Exception as exc:  # noqa: BLE001
                note = f"{type(exc).__name__}"
        if samples:
            median = round(statistics.median(samples))
            print(f"{model:<22}{median:>9}ms{min(samples):>8}ms{max(samples):>8}ms  {note}")
            summary.append((model, median, note))
        else:
            print(f"{model:<22}{'-':>10}{'-':>9}{'-':>9}  {note or '全部失败'}")

    print()
    if summary:
        fastest = min(summary, key=lambda x: x[1])
        print(f"最快模型: {fastest[0]}（中位 {fastest[1]}ms）")
        usable = [s for s in summary if not s[2]]
        if usable:
            print(f"可用且无问题: {[s[0] for s in usable]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
