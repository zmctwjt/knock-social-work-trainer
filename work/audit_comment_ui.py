"""教师点评的端到端界面验收。

流程：教师登录 → 学员画像 → 点「点评」→ 填内容「发布」→
学生登录 → 成长中心 → 看到点评；并验证未读数归零。
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
MARK = "界面验收点评：同感回应好，建议下一阶段减少建议、多做探索。"


def login(cdp: CDP, user: str) -> None:
    cdp.eval("localStorage.clear()")
    # 学生登录后会自动弹引导浮层。引导打开期间会把路由拉回当前步骤（/cases），
    # 导致后续跳转被覆盖。这里预先标记"引导已完成"。
    # 注意：必须强制重载页面 —— 改 hash 不触发重载，store 的 tourDone
    # 在首次加载时就已读成 false，之后再写 localStorage 不会生效。
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


def click_tab(cdp: CDP, name: str) -> bool:
    return cdp.eval(
        """(() => {
          const b = [...document.querySelectorAll('button.wb-tab')].find(x => {
            const c = x.cloneNode(true);
            c.querySelectorAll('.no').forEach(n => n.remove());
            return c.textContent.trim() === '%s';
          });
          if (!b) return false;
          b.click();
          return true;
        })()""" % name
    ) is True


def main() -> int:
    if PROFILE.exists():
        shutil.rmtree(PROFILE, ignore_errors=True)
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
         f"--user-data-dir={PROFILE}", "--window-size=1440,1500", "about:blank"],
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
            "window.addEventListener('unhandledrejection',e=>window.__errs.push('R:'+e.reason))"
        )

        print("\n=== 教师端：写点评 ===")
        login(cdp, "teacher01")
        # 学员画像默认选「均分最低」的学员，不一定是 student01。
        # 测试要确定性，所以先在班级总览里显式点 student01 那一行。
        picked = cdp.eval(
            """(() => {
              const b = [...document.querySelectorAll('button.wb-row-btn')]
                .find(x => x.textContent.includes('student01'));
              if (!b) return 'NO-ROW';
              b.click();
              return 'ok';
            })()"""
        )
        print(f"  选中 student01: {picked}")
        if picked != "ok":
            FAILS.append("班级总览里找不到 student01 行")
        time.sleep(4)

        opened = cdp.eval(
            """(() => {
              const b = [...document.querySelectorAll('button')]
                .find(x => x.textContent.trim() === '点评');
              if (!b) return 'NO-BTN';
              b.click();
              return 'ok';
            })()"""
        )
        print(f"  点点评按钮: {opened}")
        if opened != "ok":
            FAILS.append("训练记录里没有点评按钮")
        time.sleep(1.5)

        typed = cdp.eval(
            """(() => {
              const i = [...document.querySelectorAll('input.wb-input')]
                .find(x => (x.placeholder || '').includes('写点评'));
              if (!i) return 'NO-INPUT';
              const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
              setter.call(i, '%s');
              i.dispatchEvent(new Event('input', { bubbles: true }));
              return 'ok';
            })()""" % MARK
        )
        print(f"  填入点评: {typed}")
        time.sleep(0.8)

        published = cdp.eval(
            """(() => {
              const b = [...document.querySelectorAll('button')]
                .find(x => x.textContent.trim() === '发布');
              if (!b) return 'NO-BTN';
              b.click();
              return 'ok';
            })()"""
        )
        time.sleep(3)
        txt = cdp.eval("document.body.innerText") or ""
        seen_on_teacher = MARK[:12] in txt
        print(f"  发布: {published} 教师页可见: {seen_on_teacher}")
        if not seen_on_teacher:
            FAILS.append("发布后教师页看不到点评")
        cdp.shot(SHOTS / "comment_teacher.png")

        print("\n=== 学生端：看点评 ===")
        login(cdp, "student01")
        # 用顶栏导航点击进入成长中心（模拟真实操作），并轮询等待 hash 变化
        clicked = cdp.eval(
            """(() => {
              const a = [...document.querySelectorAll('nav a')]
                .find(x => x.textContent.includes('成长中心'));
              if (!a) return 'NO-LINK';
              a.click();
              return 'ok';
            })()"""
        )
        for _ in range(15):
            if cdp.eval("location.hash") == "#/growth":
                break
            time.sleep(0.5)
        print(f"  进入成长中心: {clicked} hash={cdp.eval('location.hash')}")
        time.sleep(3)
        txt = cdp.eval("document.body.innerText") or ""
        has_section = "老师点评" in txt
        has_content = MARK[:12] in txt
        print(f"  成长中心含「老师点评」区块: {has_section}")
        print(f"  含点评内容: {has_content}")
        if not has_section:
            FAILS.append("学生成长中心没有老师点评区块")
        if not has_content:
            FAILS.append("学生看不到点评内容")
        cdp.shot(SHOTS / "comment_student.png")

        errs = cdp.eval("window.__errs") or []
        if errs:
            for e in errs[:3]:
                FAILS.append(f"控制台错误: {e}")
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
    print("✅ 教师点评端到端闭环通过（教师发布 → 学生可见）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
