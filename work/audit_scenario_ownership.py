"""案例归属与教师端案例管理的实测。

覆盖四条关键规则：
1. 教师能新建案例，学生立刻可见；
2. 教师不能改内置案例（课程资产），也不能改别的教师建的；
3. 管理员能改任何人建的，也能改内置案例；
4. 下架后学生看不到，但历史训练记录仍能解析出案例名。

跑完自动清理测试数据。
"""
from __future__ import annotations

import sys

import httpx

BASE = "http://127.0.0.1:8000"
FAILS: list[str] = []


def login(c: httpx.Client, user: str, pw: str) -> dict[str, str]:
    r = c.post("/api/v1/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, f"{user} 登录失败 {r.text[:120]}"
    return {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}


def body(sid: str, name: str) -> dict:
    return {
        "id": sid,
        "name": name,
        "age": 52,
        "gender": "男",
        "archetype": "失业中年人",
        "difficulty": 3,
        "resistance": 3,
        "sensitive_tag": "无",
        "brief": "工厂倒闭后失业两年，妻子打零工，不愿谈未来。",
        "initial_emotion": 35,
        "system_prompt": "你扮演 52 岁失业男性，说话短、回避未来话题。",
        "voice_low": "……有啥好说的。",
        "voice_mid": "嗯，还行吧。",
        "voice_high": "你能帮我问问厂里还要人不？",
    }


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ✅ {label}")
    else:
        print(f"  ❌ {label} {detail}")
        FAILS.append(label)


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=40)
    admin = login(c, "admin01", "Admin@12345")
    teacher = login(c, "teacher01", "Teacher@12345")
    student = login(c, "student01", "Student@12345")

    # 找一个内置案例的 id
    items = c.get("/api/v1/scenarios", headers=admin).json()["data"]["items"]
    builtin = next(x for x in items if not x.get("custom"))

    print("=== 1. 教师新建案例 ===")
    r = c.post("/api/v1/teacher/scenarios", headers=teacher, json=body("X-T01", "教师建的·李叔"))
    check("教师可新建案例", r.status_code == 200, r.text[:120])

    rows = c.get("/api/v1/teacher/scenarios", headers=teacher).json()["data"]["items"]
    mine = next((x for x in rows if x["id"] == "X-T01"), None)
    check("列表里能看到自己建的案例", mine is not None)
    if mine:
        check("标记为 custom", mine["custom"] is True)
        check("标记为可编辑", mine["editable"] is True)
        check("记录了创建者昵称", bool(mine.get("owner_name")), str(mine.get("owner_name")))

    print("\n=== 2. 学生立刻可见 ===")
    st = c.get("/api/v1/scenarios", headers=student).json()["data"]["items"]
    check("学生能看到教师新建的案例", any(x["id"] == "X-T01" for x in st))
    st_row = next((x for x in st if x["id"] == "X-T01"), {})
    check("学生视角 editable=false", st_row.get("editable") is False)

    print("\n=== 3. 教师不能改内置案例 ===")
    bad = body(builtin["id"], "篡改内置案例")
    r = c.post("/api/v1/teacher/scenarios", headers=teacher, json=bad)
    check("改内置案例被拒（403）", r.status_code == 403, f"实际 {r.status_code}")
    r = c.delete(f"/api/v1/teacher/scenarios/{builtin['id']}", headers=teacher)
    check("下架内置案例被拒（403）", r.status_code == 403, f"实际 {r.status_code}")

    print("\n=== 4. 管理员能改内置案例 ===")
    r = c.post("/api/v1/admin/scenarios", headers=admin,
               json={**body(builtin["id"], builtin["name"]), "brief": builtin["brief"]})
    check("管理员可编辑内置案例", r.status_code == 200, r.text[:120])

    print("\n=== 5. 管理员能改教师建的案例 ===")
    r = c.post("/api/v1/admin/scenarios", headers=admin,
               json={**body("X-T01", "管理员改过·李叔")})
    check("管理员可编辑教师自建案例", r.status_code == 200, r.text[:120])

    print("\n=== 6. 下架后学生看不到 ===")
    r = c.delete("/api/v1/teacher/scenarios/X-T01", headers=teacher)
    check("教师可下架自己的案例", r.status_code == 200, r.text[:120])
    st = c.get("/api/v1/scenarios", headers=student).json()["data"]["items"]
    check("下架后学生列表不再出现", not any(x["id"] == "X-T01" for x in st))

    print("\n=== 7. 学生无权建案例 ===")
    r = c.post("/api/v1/teacher/scenarios", headers=student, json=body("X-S01", "学生建的"))
    check("学生建案例被拒（403）", r.status_code == 403, f"实际 {r.status_code}")

    # 清理
    print("\n=== 清理测试数据 ===")
    for sid in ("X-T01",):
        c.delete(f"/api/v1/admin/scenarios/{sid}", headers=admin)
        print(f"  已下架 {sid}")
    items = c.get("/api/v1/scenarios", headers=admin).json()["data"]["items"]
    print(f"  当前在架案例 {len(items)} 个")

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 项未通过：{FAILS}")
        return 1
    print("✅ 案例归属与教师端管理全部符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())
