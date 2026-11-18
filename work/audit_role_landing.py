"""角色化界面端到端验收。

不只验证"能不能访问"，还验证"登录后落到哪、导航有没有按角色裁剪"：
- 学生登录 → 落到 #/cases，导航 9 项且含"面谈训练"，无"管理后台"
- 教师登录 → 落到 #/teacher，导航 4 项且首项"班级看板"，无"面谈训练"
- 管理员登录 → 落到 #/admin，导航 5 项首项"管理后台"
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ui_smoke import CDP, CHROME, PORT, PROFILE, SHOTS, http_json  # noqa: E402

BASE = "http://127.0.0.1:8000"

CASES = [
    {
        "user": "student01",
        "label": "学生",
        "landing": "#/cases",
        "landing_hint": "选择本次面谈的服务对象",
        "nav_must": ["面谈训练", "成长中心"],
        "nav_not": ["管理后台", "班级看板"],
    },
    {
        "user": "teacher01",
        "label": "教师",
        "landing": "#/teacher",
        "landing_hint": "当前角色：教师",
        "nav_must": ["班级看板", "知识库"],
        "nav_not": ["管理后台", "面谈训练"],
    },
    {
        "user": "admin01",
        "label": "管理员",
        "landing": "#/admin",
        "landing_hint": "当前角色：管理员",
        "nav_must": ["管理后台", "班级看板"],
        "nav_not": ["面谈训练"],
    },
]


def wait_hash(cdp: CDP, want: str, timeout: float = 15.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if cdp.eval("location.hash") == want:
            return True
        time.sleep(0.4)
    return False


def main() -> int:
    if PROFILE.exists():
        shutil.rmtree(PROFILE, ignore_errors=True)
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
         f"--user-data-dir={PROFILE}", "--window-size=1440,900", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    failures: list[str] = []
    try:
        for _ in range(40):
            try:
                http_json("/json/version")
                break
            except Exception:
                time.sleep(0.5)
        target = http_json(f"/json/new?{BASE}/", method="PUT")
        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        time.sleep(3)

        for case in CASES:
            user = case["user"]
            print(f"\n=== {user}（应为 {case['label']}）===")
            cdp.eval("localStorage.clear()")
            cdp.eval(f"location.href = '{BASE}/#/login'")
            wait_hash(cdp, "#/login")
            time.sleep(1)

            cdp.eval(
                """(() => {
                  const row = [...document.querySelectorAll('.acc-row')]
                    .find(b => b.textContent.includes('%s'));
                  if (row) row.click();
                })()""" % user
            )
            time.sleep(0.6)
            cdp.eval("document.querySelector('button.login-submit.btn-primary').click()")

            # 登录后应落到角色专属页面
            landed = wait_hash(cdp, case["landing"], timeout=15)
            time.sleep(2)
            txt = cdp.eval("document.body.innerText") or ""
            tag = cdp.eval(
                "(() => { const el = document.querySelector('.role-tag'); "
                "return el ? el.textContent : 'NO-TAG'; })()"
            )
            print(f"  落地 hash: {cdp.eval('location.hash')}（期望 {case['landing']}，到达={landed}）")
            print(f"  顶栏角色: {tag}")
            hint_ok = case["landing_hint"] in txt
            print(f"  页面含「{case['landing_hint']}」: {hint_ok}")

            if not landed:
                failures.append(f"{user}: 未落到 {case['landing']}，实际 {cdp.eval('location.hash')}")
            if tag != case["label"]:
                failures.append(f"{user}: 角色标签 {tag}，期望 {case['label']}")
            if not hint_ok:
                failures.append(f"{user}: 落地页未见「{case['landing_hint']}」")

            # 导航按角色裁剪
            nav = cdp.eval(
                "[...document.querySelectorAll('nav a')].map(x => x.textContent.trim())"
            ) or []
            nav_text = " ".join(nav)
            print(f"  导航项({len(nav)}): {nav[:6]}")
            for must in case["nav_must"]:
                if must not in nav_text:
                    failures.append(f"{user}: 导航缺少「{must}」")
            for not_allow in case["nav_not"]:
                if not_allow in nav_text:
                    failures.append(f"{user}: 导航不应出现「{not_allow}」")

            cdp.shot(SHOTS / f"landing_{user}.png")

        cdp.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print()
    if failures:
        print(f"❌ {len(failures)} 项不符合预期：")
        for item in failures:
            print("   -", item)
        return 1
    print("✅ 角色化落地页与导航裁剪全部符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())