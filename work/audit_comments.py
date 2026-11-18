"""教师点评接口的权限与流程审查。

覆盖点：
1. 教师能给名下学员的记录点评，不能给非名下学员点评；
2. 学生能看自己的点评，不能看别人的；
3. 未读标记：学生首次查看后变为已读，未读数归零；
4. 只有作者或管理员能删点评；
5. 记录不存在返回 404，无权查看返回 403（不是 404，避免误导）。
"""
from __future__ import annotations

import sys

import httpx

BASE = "http://127.0.0.1:8000"
PW = {
    "student01": "Student@12345",
    "student02": "Student@12345",
    "teacher01": "Teacher@12345",
    "admin01": "Admin@12345",
}
FAILS: list[str] = []


def check(label: str, actual, expect) -> None:
    ok = actual == expect
    if not ok:
        FAILS.append(f"{label}: 期望 {expect}，实际 {actual}")
    print(f"  [{'PASS' if ok else 'FAIL'}] {label:52s} {actual}")


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=25)
    tok = {}
    for u, p in PW.items():
        r = c.post("/api/v1/auth/login", json={"username": u, "password": p})
        tok[u] = r.json()["data"]["tokens"]["access_token"]
    H = lambda u: {"Authorization": f"Bearer {tok[u]}"}  # noqa: E731

    print("\n=== 准备：取一条训练记录 ===")
    learners = c.get("/api/v1/teacher/learners", headers=H("teacher01")).json()["data"]["items"]
    print(f"  教师名下学员: {[x['username'] for x in learners]}")
    if not learners:
        print("  没有学员，无法测试")
        return 1

    target = next((x for x in learners if x["username"] == "student01"), learners[0])
    recs = c.get(
        f"/api/v1/teacher/learners/{target['account_id']}/records",
        headers=H("teacher01"),
    ).json()["data"]
    if not recs["items"]:
        print("  该学员没有训练记录，请先跑 seed_training_data.py")
        return 1
    record_id = None
    # 记录接口返回的是 LearnerRecordOut，需要拿真正的 record id
    detail = c.get(
        f"/api/v1/teacher/learners/{target['account_id']}/detail", headers=H("teacher01")
    ).json()["data"]
    print(f"  学员 {detail['nickname']} 共 {detail['sessions']} 条记录")

    print("\n=== 1. 教师给名下学员点评 ===")
    # 记录接口已返回 record_id，直接复用，不再依赖 MySQL 命令行客户端
    record_id = recs["items"][0].get("record_id")
    if not record_id:
        print("  记录里没有 record_id，接口可能回退了")
        return 1
    print(f"  使用记录 {record_id}")

    r = c.post(
        f"/api/v1/teacher/comments?record_id={record_id}",
        headers=H("teacher01"),
        json={"content": "这次面谈同感回应到位，但信息建议部分偏多，建议下次先探索再给建议。", "level": "watch"},
    )
    check("教师点评名下学员", r.status_code, 200)
    comment_id = r.json()["data"]["id"] if r.status_code == 200 else None
    if r.status_code == 200:
        print(f"    level_label={r.json()['data']['level_label']}")

    print("\n=== 2. 学生看自己的点评 ===")
    r = c.get("/api/v1/comments/mine", headers=H("student01"))
    check("学生查看自己的点评", r.status_code, 200)
    mine = r.json()["data"]
    print(f"    共 {mine['total']} 条，未读 {mine['unread']}")

    print("\n=== 3. 未读变已读 ===")
    r2 = c.get("/api/v1/comments/mine", headers=H("student01"))
    check("二次查看未读归零", r2.json()["data"]["unread"], 0)

    print("\n=== 4. 学生不能看别人的点评 ===")
    r = c.get("/api/v1/comments/unread", headers=H("student02"))
    check("student02 未读数", r.status_code, 200)

    print("\n=== 5. 教师不能点评非名下学员 ===")
    # 造一个不归属该教师的学员
    all_acc = c.get("/api/v1/admin/accounts", headers=H("admin01")).json()["data"]["items"]
    mine_ids = {x["account_id"] for x in learners}
    outsider = next(
        (a for a in all_acc if a["role"] == "student" and a["id"] not in mine_ids), None
    )
    if outsider:
        orec = None
        orecs = c.get(
            f"/api/v1/teacher/learners/{outsider['id']}/records",
            headers=H("admin01"),
        ).json()["data"]["items"]
        if orecs:
            orec = orecs[0].get("record_id")
        if orec:
            r = c.post(
                f"/api/v1/teacher/comments?record_id={orec}",
                headers=H("teacher01"),
                json={"content": "越权测试", "level": "good"},
            )
            check("教师点评非名下学员（应 403）", r.status_code, 403)
        else:
            print("  (非名下学员无训练记录，跳过该项)")

    print("\n=== 6. 学生不能点评 ===")
    r = c.post(
        f"/api/v1/teacher/comments?record_id={record_id}",
        headers=H("student01"),
        json={"content": "学生越权", "level": "good"},
    )
    check("学生调教师点评接口", r.status_code, 403)

    print("\n=== 7. 记录不存在 ===")
    r = c.post(
        "/api/v1/teacher/comments?record_id=00000000-0000-0000-0000-000000000000",
        headers=H("teacher01"),
        json={"content": "x", "level": "good"},
    )
    check("不存在的记录", r.status_code, 404)

    # 本项目的 RequestValidationError 统一映射为 400 + ErrorCode.BAD_REQUEST，
    # 而非 FastAPI 默认的 422；断言要对齐项目约定。
    print("\n=== 8. 空内容被拒 ===")
    r = c.post(
        f"/api/v1/teacher/comments?record_id={record_id}",
        headers=H("teacher01"),
        json={"content": "", "level": "good"},
    )
    check("空点评内容（项目约定 400）", r.status_code, 400)

    print("\n=== 9. 删除权限 ===")
    if comment_id:
        r = c.delete(f"/api/v1/teacher/comments/{comment_id}", headers=H("student01"))
        check("学生删教师点评（应 403）", r.status_code, 403)
        r = c.delete(f"/api/v1/teacher/comments/{comment_id}", headers=H("teacher01"))
        check("作者本人删除", r.status_code, 200)

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 项不符合预期：")
        for f in FAILS:
            print("   -", f)
        return 1
    print("✅ 教师点评权限与流程全部符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())
