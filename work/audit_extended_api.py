"""扩展接口的权限与健壮性审查。

重点不是"接口能返回 200"，而是：
1. 越权必须 403（教师看非名下学员、学生看管理端、访客看教师端）；
2. 参数越界必须被夹住（days、limit、ID 格式）；
3. 不存在的资源必须 404 而不是 500；
4. 批量操作要能容错（部分失败不影响其余）。
"""
from __future__ import annotations

import sys

import httpx

BASE = "http://127.0.0.1:8000"
PW = {"student01": "Student@12345", "teacher01": "Teacher@12345",
      "student02": "Student@12345", "admin01": "Admin@12345"}

FAILS: list[str] = []


def check(label: str, actual, expect) -> None:
    ok = actual == expect
    if not ok:
        FAILS.append(f"{label}: 期望 {expect}，实际 {actual}")
    print(f"  [{'PASS' if ok else 'FAIL'}] {label:56s} {actual}")


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=25)
    tok = {u: c.post("/api/v1/auth/login", json={"username": u, "password": p})
           .json()["data"]["tokens"]["access_token"] for u, p in PW.items()}
    H = lambda u: {"Authorization": f"Bearer {tok[u]}"}  # noqa: E731

    print("\n=== 教师端：名下 vs 非名下 ===")
    mine = c.get("/api/v1/teacher/learners", headers=H("teacher01")).json()["data"]["items"]
    mine_ids = {x["account_id"] for x in mine}
    print(f"  教师名下学员数: {len(mine)}")
    all_acc = c.get("/api/v1/admin/accounts", headers=H("admin01")).json()["data"]["items"]
    outsider = next((a for a in all_acc if a["role"] == "student"
                     and a["id"] not in mine_ids), None)
    if mine:
        r = c.get(f"/api/v1/teacher/learners/{mine[0]['account_id']}/detail", headers=H("teacher01"))
        check("教师看名下学员画像", r.status_code, 200)
    if outsider:
        r = c.get(f"/api/v1/teacher/learners/{outsider['id']}/detail", headers=H("teacher01"))
        check("教师看非名下学员画像（应 403）", r.status_code, 403)
        check("  └ 错误码", r.json()["code"], 40301)

    print("\n=== 学生/访客禁止进入教师端与管理端 ===")
    for path in ("/api/v1/teacher/trend", "/api/v1/admin/trend",
                 "/api/v1/admin/accounts/bulk-active"):
        for who in ("student01",):
            r = c.get(path, headers=H(who)) if "bulk" not in path else c.post(
                path, headers=H(who), json={"account_ids": [], "active": True})
            check(f"{who} {'GET' if 'bulk' not in path else 'POST'} {path}", r.status_code, 403)
    guest = c.post("/api/v1/auth/guest", json={"nickname": "审查"}).json()["data"]["tokens"]["access_token"]
    r = c.get("/api/v1/teacher/trend", headers={"Authorization": f"Bearer {guest}"})
    check("访客 GET /teacher/trend", r.status_code, 403)

    print("\n=== 参数越界要被夹住而不是报错 ===")
    for days, label in ((0, "days=0"), (99999, "days=99999"), (-5, "days=-5")):
        r = c.get(f"/api/v1/admin/trend?days={days}", headers=H("admin01"))
        body = r.json()
        eff = body["data"]["days"] if r.status_code == 200 else None
        ok = r.status_code == 200 and 1 <= (eff or 0) <= 180
        if not ok:
            FAILS.append(f"admin/trend {label}: 未夹住，返回 {r.status_code} eff={eff}")
        print(f"  [{'PASS' if ok else 'FAIL'}] admin/trend {label:14s} 生效 days={eff}")

    print("\n=== 不存在的资源应 404 而非 500 ===")
    r = c.get("/api/v1/teacher/learners/00000000-0000-0000-0000-000000000000/detail",
              headers=H("admin01"))
    check("不存在的学员画像", r.status_code, 404)
    r = c.delete("/api/v1/admin/script-lines/00000000-0000-0000-0000-000000000000",
                 headers=H("admin01"))
    check("不存在的台词删除", r.status_code, 404)

    print("\n=== 批量操作容错 ===")
    real = next(a["id"] for a in all_acc if a["role"] == "student")
    payload = {"account_ids": [real, "00000000-0000-0000-0000-000000000000"], "active": True}
    r = c.post("/api/v1/admin/accounts/bulk-active", headers=H("admin01"), json=payload)
    if r.status_code == 200:
        d = r.json()["data"]
        ok = d["updated"] >= 1 and d["failed"] >= 1
        print(f"  [{'PASS' if ok else 'FAIL'}] 批量含无效 ID：updated={d['updated']} failed={d['failed']}")
        if not ok:
            FAILS.append(f"批量操作容错异常：{d}")
    else:
        FAILS.append(f"批量操作返回 {r.status_code}")

    print("\n=== 趋势接口返回结构完整 ===")
    r = c.get("/api/v1/admin/trend?days=7", headers=H("admin01"))
    d = r.json()["data"]
    ok = (len(d["points"]) == 7 and "role_distribution" in d
          and isinstance(d["dimensions"], list) and len(d["dimensions"]) == 6)
    print(f"  [{'PASS' if ok else 'FAIL'}] points={len(d['points'])} dims={len(d['dimensions'])} "
          f"roles={len(d['role_distribution'])}")
    if not ok:
        FAILS.append(f"admin/trend 结构不完整：{list(d)}")

    r = c.get("/api/v1/teacher/trend?days=7", headers=H("teacher01"))
    d = r.json()["data"]
    ok = len(d["points"]) == 7 and len(d["dimensions"]) == 6
    print(f"  [{'PASS' if ok else 'FAIL'}] teacher/trend points={len(d['points'])} dims={len(d['dimensions'])}")
    if not ok:
        FAILS.append("teacher/trend 结构不完整")

    print("\n=== AI 日志聚合指标 ===")
    r = c.get("/api/v1/admin/ai-logs?limit=5", headers=H("admin01"))
    d = r.json()["data"]
    ok = all(k in d for k in ("items", "total", "success_rate", "avg_latency_ms"))
    print(f"  [{'PASS' if ok else 'FAIL'}] keys={sorted(d)} success_rate={d.get('success_rate')}")
    if not ok:
        FAILS.append("ai-logs 缺少聚合字段")

    print("\n=== 危机词禁用仍受保护 ===")
    r = c.delete("/api/v1/admin/rule-words/crisis/不想活", headers=H("admin01"))
    check("禁用危机词", r.status_code, 403)

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 项不符合预期：")
        for f in FAILS:
            print("   -", f)
        return 1
    print("✅ 扩展接口权限与健壮性全部符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())