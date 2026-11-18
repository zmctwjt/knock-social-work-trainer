"""教师工作台与管理后台的界面验收。

检查每个标签页能否正常渲染、关键数据是否出现、控制台有无报错。
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
FAILS: list[str] = []
ERRORS: list[str] = []


def login(cdp: CDP, user: str) -> None:
    cdp.eval("localStorage.clear()")
    cdp.eval(f"location.href = '{BASE}/#/login'")
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
    time.sleep(6)


def visit_tabs(cdp: CDP, tabs: list[str], must_contain: dict[str, str], who: str) -> None:
    for tab in tabs:
        # 标签按钮内含 <span class="no">01</span> 序号，textContent 不等于纯标签名，
        # 因此用 wb-tab 选择器 + 去掉序号后比较
        clicked = cdp.eval(
            """(() => {
              const want = '%s';
              const b = [...document.querySelectorAll('button.wb-tab')]
                .find(x => {
                  const clone = x.cloneNode(true);
                  clone.querySelectorAll('.no').forEach(n => n.remove());
                  return clone.textContent.trim() === want;
                });
              if (!b) return 'NO-TAB';
              b.click();
              return 'ok';
            })()""" % tab
        )
        time.sleep(3)
        txt = cdp.eval("document.body.innerText") or ""
        need = must_contain.get(tab, "")
        ok = clicked == "ok" and (need in txt if need else True)
        print(f"  [{'PASS' if ok else 'FAIL'}] {who} 标签「{tab}」 clicked={clicked} 关键内容={need in txt if need else 'n/a'}")
        if not ok:
            FAILS.append(f"{who} 标签「{tab}」渲染异常（clicked={clicked}）")
        # 页面出现空白/报错关键字时记一笔
        for bad in ("Uncaught", "Something went wrong", "Cannot read properties"):
            if bad in txt:
                ERRORS.append(f"{who}/{tab}: 页面出现 {bad}")
        cdp.shot(SHOTS / f"tab_{who}_{tab}.png")


def main() -> int:
    if PROFILE.exists():
        shutil.rmtree(PROFILE, ignore_errors=True)
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
         f"--user-data-dir={PROFILE}", "--window-size=1440,1400", "about:blank"],
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
        cdp.eval(
            "window.__errs=[];"
            "window.addEventListener('error',e=>window.__errs.push(String(e.message)));"
            "window.addEventListener('unhandledrejection',e=>window.__errs.push('REJ:'+String(e.reason)))"
        )

        print("\n=== 教师工作台 ===")
        login(cdp, "teacher01")
        visit_tabs(
            cdp,
            ["班级总览", "学员画像", "训练趋势", "内容查阅"],
            {"班级总览": "名下学员", "训练趋势": "班级六维均值", "内容查阅": "技巧卡"},
            "teacher",
        )

        print("\n=== 管理后台 ===")
        login(cdp, "admin01")
        visit_tabs(
            cdp,
            ["运行概览", "账号管理", "平台趋势", "内容维护", "判定词表", "台词节点", "操作审计"],
            {
                "运行概览": "AI 服务状态",
                "账号管理": "新建账号",
                "平台趋势": "角色分布",
                "内容维护": "技巧卡",
                "判定词表": "九个词表分组",
                "台词节点": "已维护台词",
            },
            "admin",
        )

        errs = cdp.eval("window.__errs") or []
        if errs:
            for e in errs[:5]:
                ERRORS.append(f"控制台: {e}")
        cdp.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print()
    if FAILS or ERRORS:
        if FAILS:
            print(f"❌ {len(FAILS)} 项页面问题：")
            for f in FAILS:
                print("   -", f)
        if ERRORS:
            print(f"⚠️ {len(ERRORS)} 项运行时报错：")
            for e in ERRORS:
                print("   -", e)
        return 1
    print("✅ 教师工作台与管理后台全部标签页渲染正常，无控制台错误")
    return 0


if __name__ == "__main__":
    sys.exit(main())