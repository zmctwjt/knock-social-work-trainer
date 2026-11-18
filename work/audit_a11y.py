"""无障碍（A11y）审查：标签页键盘可达性与 ARIA 完整性。

检查三件事：
1. role=tablist / tab / tabpanel 三者关联完整（id ↔ aria-controls ↔ aria-labelledby）；
2. 左右方向键能在标签间切换，Home/End 跳首尾；
3. 非当前标签不进入 Tab 序列（tabIndex=-1），避免键盘用户被逐个标签卡住。

用 CDP 的 Input.dispatchKeyEvent 发真实按键，而不是 JS 合成事件——
后者不触发浏览器默认行为，测不出真实键盘路径。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ui_smoke import CDP, CHROME, PORT, PROFILE, http_json  # noqa: E402

BASE = "http://127.0.0.1:8000"
FAILS: list[str] = []

KEYS = {
    "ArrowRight": 39,
    "ArrowLeft": 37,
    "Home": 36,
    "End": 35,
}


def press(cdp: CDP, key: str) -> None:
    """发真实按键事件（rawKeyDown + keyUp），会触发浏览器默认行为与 React 处理。"""
    code = KEYS[key]
    cdp.send(
        "Input.dispatchKeyEvent",
        type="rawKeyDown", windowsVirtualKeyCode=code, nativeVirtualKeyCode=code, key=key,
    )
    cdp.send(
        "Input.dispatchKeyEvent",
        type="keyUp", windowsVirtualKeyCode=code, nativeVirtualKeyCode=code, key=key,
    )
    time.sleep(0.6)


def login(cdp: CDP, user: str) -> None:
    cdp.eval("localStorage.clear()")
    cdp.eval("localStorage.setItem('knock.tourDone','1')")
    cdp.eval(f"location.href = '{BASE}/#/login'")
    time.sleep(1)
    cdp.eval("location.reload()")
    time.sleep(4)
    cdp.eval(
        """(() => {
          const row = [...document.querySelectorAll('.acc-row')]
            .find(b => b.textContent.includes('%s'));
          if (row) row.click();
        })()""" % user
    )
    time.sleep(0.8)
    cdp.eval("document.querySelector('button.login-submit.btn-primary').click()")
    time.sleep(7)


def audit_tabs(cdp: CDP, label: str) -> None:
    """通用检查：ARIA 关联 + 键盘导航。"""
    print(f"\n=== {label} ===")

    aria = cdp.eval(
        """(() => {
          const list = document.querySelector('[role="tablist"]');
          if (!list) return null;
          const tabs = [...list.querySelectorAll('[role="tab"]')];
          return tabs.map(t => ({
            id: t.id,
            controls: t.getAttribute('aria-controls'),
            selected: t.getAttribute('aria-selected'),
            tabIndex: t.tabIndex,
            panelExists: !!document.getElementById(t.getAttribute('aria-controls') || ''),
          }));
        })()"""
    )
    if not aria:
        FAILS.append(f"{label}: 找不到 tablist")
        return

    print(f"  标签数: {len(aria)}")
    for t in aria:
        if not t["id"]:
            FAILS.append(f"{label}: 标签缺少 id")
        if not t["controls"]:
            FAILS.append(f"{label}: {t['id']} 缺少 aria-controls")
        elif not t["panelExists"]:
            FAILS.append(f"{label}: {t['id']} 的 aria-controls 指向不存在的面板")

    selected = [t for t in aria if t["selected"] == "true"]
    if len(selected) != 1:
        FAILS.append(f"{label}: 应恰好 1 个选中标签，实际 {len(selected)}")

    # 非当前标签不应是 tab stop
    bad_stops = [t["id"] for t in aria if t["selected"] != "true" and t["tabIndex"] != -1]
    if bad_stops:
        FAILS.append(f"{label}: 非选中标签仍可 Tab 聚焦 {bad_stops}")
    else:
        print("  非选中标签 tabIndex=-1 ✓")

    # tabpanel 的 aria-labelledby 要指回标签
    panel_ok = cdp.eval(
        """(() => {
          const p = document.querySelector('[role="tabpanel"]');
          if (!p) return null;
          const lb = p.getAttribute('aria-labelledby');
          const target = lb ? document.getElementById(lb) : null;
          return { id: p.id, labelledby: lb, resolved: !!target };
        })()"""
    )
    if not panel_ok:
        FAILS.append(f"{label}: 找不到 tabpanel")
    elif not panel_ok["resolved"]:
        FAILS.append(f"{label}: tabpanel 的 aria-labelledby 无效")
    else:
        print(f"  tabpanel 关联有效: {panel_ok['labelledby']} ✓")

    # 键盘导航：聚焦当前标签后按方向键
    first_id = selected[0]["id"] if selected else aria[0]["id"]
    cdp.eval(f"document.getElementById('{first_id}').focus()")
    time.sleep(0.3)
    before = cdp.eval("document.activeElement.id")

    press(cdp, "ArrowRight")
    after_right = cdp.eval("document.activeElement.id")
    changed = after_right != before
    print(f"  ArrowRight: {before} → {after_right} {'✓' if changed else '✗'}")
    if not changed:
        FAILS.append(f"{label}: 方向键没有切换标签")

    press(cdp, "ArrowLeft")
    back = cdp.eval("document.activeElement.id")
    print(f"  ArrowLeft : {after_right} → {back} {'✓' if back == before else '✗'}")
    if back != before:
        FAILS.append(f"{label}: 左方向键没有回到原标签")

    press(cdp, "End")
    at_end = cdp.eval("document.activeElement.id")
    print(f"  End       : → {at_end} {'✓' if at_end == aria[-1]['id'] else '✗'}")
    if at_end != aria[-1]["id"]:
        FAILS.append(f"{label}: End 未跳到最后一项")

    press(cdp, "Home")
    at_home = cdp.eval("document.activeElement.id")
    print(f"  Home      : → {at_home} {'✓' if at_home == aria[0]['id'] else '✗'}")
    if at_home != aria[0]["id"]:
        FAILS.append(f"{label}: Home 未跳到第一项")


def main() -> int:
    if PROFILE.exists():
        shutil.rmtree(PROFILE, ignore_errors=True)
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
         f"--user-data-dir={PROFILE}", "--window-size=1440,1200", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
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

        # 知识库（未登录也可访问）
        cdp.eval(f"location.href='{BASE}/#/knowledge'")
        time.sleep(1)
        cdp.eval("location.reload()")
        time.sleep(5)
        audit_tabs(cdp, "知识库标签")

        # 教师工作台
        login(cdp, "teacher01")
        time.sleep(2)
        audit_tabs(cdp, "教师工作台标签")

        # 管理后台
        login(cdp, "admin01")
        time.sleep(2)
        audit_tabs(cdp, "管理后台标签")

        cdp.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 项：")
        for f in FAILS:
            print("   -", f)
        return 1
    print("✅ 标签页无障碍：ARIA 关联完整，方向键/Home/End 导航可用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
