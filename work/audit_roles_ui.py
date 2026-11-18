"""三角色登录与页面隔离的浏览器实测。

对每个角色：清空登录态 → 登录页 → 填入账号 → 提交 → 检查顶栏角色标签 →
访问教师工作台与管理后台，验证服务端权限确实生效。

关键实现细节：
- 项目用 HashRouter，Chrome 的 /json/new?URL 会丢掉 hash，因此先开根路径再用 JS 赋值；
- 登录后有 nav('/cases') 跳转，需等待 hash 稳定；
- 顶栏"登录"文本同时用于 tab 与提交按钮，必须选 `button.login-submit.btn-primary`；
- 导航后轮询等待目标 hash 出现，而不是固定 sleep。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ui_smoke import BASE, CDP, CHROME, PORT, PROFILE, SHOTS, http_json  # noqa: E402

BASE = "http://127.0.0.1:8000"
CASES = [
    ("student01", "学生"),
    ("teacher01", "教师"),
    ("admin01", "管理员"),
]


def wait_hash(cdp: CDP, want: str, timeout: float = 12.0) -> bool:
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

        for username, expect_label in CASES:
            print(f"\n--- {username}（应为 {expect_label}）---")
            cdp.eval("localStorage.clear()")
            cdp.eval(f"location.href = '{BASE}/#/login'")
            if not wait_hash(cdp, "#/login"):
                failures.append(f"{username}: 没能进入登录页")
                continue
            time.sleep(1)

            picked = cdp.eval(
                """(() => {
                  const row = [...document.querySelectorAll('.acc-row')]
                    .find(b => b.textContent.includes('%s'));
                  if (!row) return 'NO-DEMO';
                  row.click();
                  return 'picked';
                })()""" % username
            )
            clicked = cdp.eval(
                """(() => {
                  const btn = document.querySelector('button.login-submit.btn-primary');
                  if (!btn) return 'NO-BTN';
                  btn.click();
                  return 'clicked';
                })()"""
            )
            wait_hash(cdp, "#/cases", timeout=12)
            time.sleep(1)
            label = cdp.eval(
                "(() => { const el = document.querySelector('.role-tag'); "
                "return el ? el.textContent : 'NO-TAG'; })()"
            )
            print(f"  fill={picked} click={clicked} 顶栏角色标签={label}")
            if label != expect_label:
                failures.append(f"{username}: 期望角色标签 {expect_label}，实际 {label}")

            # 教师工作台：先确保登录跳转彻底完成，再改 hash，最后轮询等待
            wait_hash(cdp, "#/cases", timeout=12)
            time.sleep(2)
            cdp.eval("location.hash = '#/teacher'")
            reached_teacher = wait_hash(cdp, "#/teacher", timeout=12)
            # 第一次可能被 React 的挂载 effect 覆盖，重试一次
            if not reached_teacher:
                time.sleep(1)
                cdp.eval("location.hash = '#/teacher'")
                reached_teacher = wait_hash(cdp, "#/teacher", timeout=12)
            time.sleep(2)
            txt = cdp.eval("document.body.innerText") or ""
            has_workspace = "教师工作台 · TEACHER" in txt
            print(f"  教师工作台: hash到达={reached_teacher} 页面渲染={has_workspace}")
            if expect_label in ("教师", "管理员") and not has_workspace:
                failures.append(f"{username}: 应可访问教师工作台")
            if expect_label == "学生" and has_workspace:
                failures.append(f"{username}: 学生不应看到教师工作台")

            # 管理后台
            cdp.eval("location.hash = '#/admin'")
            reached_admin = wait_hash(cdp, "#/admin")
            time.sleep(2)
            txt = cdp.eval("document.body.innerText") or ""
            admin_ok = "管理后台" in txt and "欢迎回来" in txt
            admin_denied = "无权限访问" in txt
            print(f"  管理后台: hash到达={reached_admin} 可访问={admin_ok} 被拦={admin_denied}")
            if expect_label == "管理员" and not admin_ok:
                failures.append(f"{username}: 应可访问管理后台")
            if expect_label != "管理员" and admin_ok:
                failures.append(f"{username}: 不应访问管理后台")

            cdp.shot(SHOTS / f"role_{username}.png")

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
    print("✅ 三角色登录与页面隔离全部符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())
