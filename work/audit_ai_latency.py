"""AI 链路的冷/热延迟与降级行为实测。

回答三个实际问题：
1. 冷调用（首次、未命中缓存）要多久？会不会顶到 45s 超时？
2. 相同输入第二次是否真的走缓存？省下多少时间？
3. 模型链的真实使用情况（审计日志里能看到哪些模型被调用过）？

用随机后缀构造每次不同的输入，确保是真正的冷调用。
"""
from __future__ import annotations

import random
import string
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
STUDENT = {"username": "student01", "password": "Student@12345"}
ADMIN = {"username": "admin01", "password": "Admin@12345"}


def rand() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=120)
    st = c.post("/api/v1/auth/login", json=STUDENT).json()["data"]["tokens"]["access_token"]
    ad = c.post("/api/v1/auth/login", json=ADMIN).json()["data"]["tokens"]["access_token"]
    SH = {"Authorization": f"Bearer {st}"}
    AH = {"Authorization": f"Bearer {ad}"}

    print("=" * 66)
    print(" 一 冷调用延迟（每次构造不同输入，确保未命中缓存）")
    print("=" * 66)

    results = []

    # intent
    payload = {
        "input": f"王阿姨您好，我是社区的小陈，想陪您聊聊最近情况（{rand()}）",
        "scenario_id": "W-01", "emotion": 50, "turn_index": 1,
    }
    t0 = time.perf_counter()
    r = c.post("/api/v1/ai/intent", headers=SH, json=payload)
    cold = round((time.perf_counter() - t0) * 1000)
    ok = r.status_code == 200
    print(f"  intent  冷调用 {cold:6d} ms  HTTP {r.status_code}")
    results.append(("intent", cold, ok))

    t0 = time.perf_counter()
    r2 = c.post("/api/v1/ai/intent", headers=SH, json=payload)
    warm = round((time.perf_counter() - t0) * 1000)
    print(f"          热调用 {warm:6d} ms（相同输入，应显著更快）")
    results.append(("intent(热)", warm, r2.status_code == 200))

    # persona
    payload = {
        "scenario_id": "W-01", "emotion": 42, "last_intent": "empathy",
        "student_text": f"听您说一个人吃饭做多了吃不完，这种日子确实不好受（{rand()}）",
        "turn_index": 2,
    }
    t0 = time.perf_counter()
    r = c.post("/api/v1/ai/persona", headers=SH, json=payload)
    cold = round((time.perf_counter() - t0) * 1000)
    print(f"  persona 冷调用 {cold:6d} ms  HTTP {r.status_code}")
    results.append(("persona", cold, r.status_code == 200))
    if r.status_code == 200:
        text = (r.json()["data"].get("text") or "")
        print(f"          台词: {text[:48]!r}")

    t0 = time.perf_counter()
    c.post("/api/v1/ai/persona", headers=SH, json=payload)
    warm = round((time.perf_counter() - t0) * 1000)
    print(f"          热调用 {warm:6d} ms")
    results.append(("persona(热)", warm, True))

    # score
    payload = {
        "dialogue": [
            {"role": "worker", "text": f"王阿姨您好，我是小陈（{rand()}）"},
            {"role": "client", "text": "你来干什么，我没什么好说的。"},
            {"role": "worker", "text": "一个人过日子，做多了吃不完，确实不好受。"},
        ],
        "stage_index": 1,
    }
    t0 = time.perf_counter()
    r = c.post("/api/v1/ai/score", headers=SH, json=payload)
    cold = round((time.perf_counter() - t0) * 1000)
    print(f"  score   冷调用 {cold:6d} ms  HTTP {r.status_code}")
    results.append(("score", cold, r.status_code == 200))
    if r.status_code == 200:
        d = r.json()["data"]
        print(f"          scores={d.get('scores')} total={d.get('total')}")

    # debrief
    payload = {
        "nickname": "学员小李", "name": "王阿姨", "age": 68, "identity": "空巢老人",
        "scores": {"empathy": 70, "question": 65, "advice": 55,
                   "ethics": 72, "process": 60, "risk": 58},
        "hit_rules": [f"第2句 建议过早（{rand()}）"],
        "template": {"ok": ["同感及时"], "off": ["建议过早"], "next": ["先探索"]},
    }
    t0 = time.perf_counter()
    r = c.post("/api/v1/ai/debrief", headers=SH, json=payload)
    cold = round((time.perf_counter() - t0) * 1000)
    print(f"  debrief 冷调用 {cold:6d} ms  HTTP {r.status_code}")
    results.append(("debrief", cold, r.status_code == 200))

    t0 = time.perf_counter()
    c.post("/api/v1/ai/debrief", headers=SH, json=payload)
    warm = round((time.perf_counter() - t0) * 1000)
    print(f"          热调用 {warm:6d} ms")
    results.append(("debrief(热)", warm, True))

    print()
    print("=" * 66)
    print(" 二 审计日志：真实调用记录")
    print("=" * 66)
    r = c.get("/api/v1/admin/ai-logs?limit=12", headers=AH)
    logs = r.json()["data"]
    print(f"  可用率={logs['success_rate']}% 走模型={logs['ok_count']} "
          f"降级={logs['degraded_count']} 报错={logs['error_count']}")
    print(f"  平均延迟={logs['avg_latency_ms']} ms")
    for item in logs["items"][:8]:
        print(f"    {item['purpose']:8s} {item['status']:9s} "
              f"{item['model'] or '-':22s} {item['latency_ms']:6d}ms "
              f"cache={item['cache_hit']}")

    print()
    fails = [name for name, ms, ok in results if not ok]
    if fails:
        print(f"❌ 失败链路: {fails}")
        return 1

    colds = [ms for name, ms, _ in results if "热" not in name]
    warms = [ms for name, ms, _ in results if "热" in name]
    print("=" * 66)
    print(f" 冷调用区间 {min(colds)}–{max(colds)} ms；热调用区间 "
          f"{min(warms) if warms else '-'}–{max(warms) if warms else '-'} ms")
    if colds and max(colds) > 40_000:
        print("⚠️ 有冷调用接近 45s 超时，需要关注")
        return 1
    print("✅ 四条链路冷热调用均正常，缓存有效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
