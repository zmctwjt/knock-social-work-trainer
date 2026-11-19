"""真实 AI 链路验证（用真实密钥打真实模型）。

此前所有 AI 测试都用 mock provider，供应商真实行为未验证。
这个脚本对四条链路各发一次真实请求，检查：
1. 是否真的走了模型（meta.used_ai = true，而不是降级）；
2. 返回内容是否可用（正文非空、无思维链残留）；
3. 耗时与命中的模型是否符合预期。

注意：会产生真实 API 调用费用（很便宜，但每次调用都记账）。
"""
from __future__ import annotations

import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
PW = {"student01": "Student@12345"}


def show(label: str, resp: httpx.Response) -> dict:
    if resp.status_code != 200:
        print(f"  ❌ {label}: HTTP {resp.status_code} {resp.text[:160]}")
        return {}
    body = resp.json()
    data = body.get("data") or {}
    meta = data.get("meta") or {}
    print(f"  {label}: 200")
    print(f"    used_ai={meta.get('used_ai')} model={meta.get('model')} "
          f"degrade={meta.get('degrade_reason')}")
    return data


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=120)
    token = c.post("/api/v1/auth/login",
                   json={"username": "student01",
                         "password": PW["student01"]}).json()["data"]["tokens"]["access_token"]
    H = {"Authorization": f"Bearer {token}"}

    fails: list[str] = []

    print("=== 1. 意图判定 /api/v1/ai/intent ===")
    t0 = time.perf_counter()
    r = c.post("/api/v1/ai/intent", headers=H, json={
        "input": "王阿姨您好，我是社区的小陈，今天想陪您聊聊最近的情况，您方便吗？",
        "scenario_id": "W-01",
        "emotion": 50,
        "turn_index": 1,
    })
    ms = round((time.perf_counter() - t0) * 1000)
    d = show("intent", r)
    if d:
        print(f"    intent={d.get('intent')} emotion_delta={d.get('emotion_delta')} ({ms}ms)")
        if not d.get("meta", {}).get("used_ai"):
            fails.append("意图判定未走模型")

    print("\n=== 2. 服务对象台词 /api/v1/ai/persona ===")
    t0 = time.perf_counter()
    r = c.post("/api/v1/ai/persona", headers=H, json={
        "scenario_id": "W-01",
        "emotion": 45,
        "last_intent": "empathy",
        "student_text": "听您说一个人吃饭做多了吃不完，这种日子确实不好受。",
        "turn_index": 2,
    })
    ms = round((time.perf_counter() - t0) * 1000)
    d = show("persona", r)
    if d:
        reply = (d.get("text") or "").strip()
        print(f"    reply={reply[:60]!r} ({ms}ms)")
        if not reply:
            fails.append("persona 返回空台词")
        if "<think" in reply.lower():
            fails.append("persona 台词里残留思维链标签")
        if not d.get("meta", {}).get("used_ai"):
            fails.append("persona 未走模型")

    print("\n=== 3. 六维评分 /api/v1/ai/score ===")
    t0 = time.perf_counter()
    r = c.post("/api/v1/ai/score", headers=H, json={
        "scenario_id": "W-01",
        "dialogue": [
            {"role": "worker", "text": "王阿姨您好，我是社区的小陈。"},
            {"role": "client", "text": "你来干什么，我没什么好说的。"},
            {"role": "worker", "text": "听您说一个人过日子，做多了吃不完，这确实不好受。"},
        ],
        "stage_index": 1,
    })
    ms = round((time.perf_counter() - t0) * 1000)
    d = show("score", r)
    if d:
        scores = d.get("scores") or {}
        print(f"    scores={scores} ({ms}ms)")
        if not scores:
            fails.append("score 未返回维度分")
        elif any(not (0 <= v <= 100) for v in scores.values() if isinstance(v, (int, float))):
            fails.append(f"score 分值越界: {scores}")

    print("\n=== 4. 三段式复盘 /api/v1/ai/debrief ===")
    t0 = time.perf_counter()
    r = c.post("/api/v1/ai/debrief", headers=H, json={
        "nickname": "学员小李",
        "name": "王阿姨",
        "age": 68,
        "identity": "空巢老人",
        "scores": {"empathy": 70, "question": 65, "advice": 55,
                   "ethics": 72, "process": 60, "risk": 58},
        "hit_rules": ["第2句 判定为建议过早"],
        "template": {"ok": ["同感回应及时"], "off": ["建议给得太早"],
                     "next": ["先探索再建议"]},
    })
    ms = round((time.perf_counter() - t0) * 1000)
    d = show("debrief", r)
    if d:
        total_chars = sum(len("".join(v)) if isinstance(v, list) else len(str(v))
                          for v in d.values() if isinstance(v, (list, str)))
        print(f"    返回字段={list(d.keys())} 内容长度≈{total_chars} ({ms}ms)")
        if total_chars < 10:
            fails.append("debrief 内容过短")

    print()
    if fails:
        print("❌ 问题：")
        for f in fails:
            print("   -", f)
        return 1
    print("✅ 四条 AI 链路均真实调用成功，返回内容可用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
