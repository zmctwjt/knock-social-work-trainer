"""教师端「案例管理」的界面端到端验证。

API 层已由 audit_scenario_ownership.py 覆盖（12 项权限规则），
这里验证界面真的能用：
1. 教师登录后能进「案例管理」页签；
2. 表单填完点保存，列表出现新案例；
3. 内置案例行显示「只读」、没有编辑/下架按钮（权限在界面上就受限）；
4. 学生端选角页能看到教师新建的案例。

跑完自动清理测试数据。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from ui_smoke import BASE, SHOTS, launch_chrome, open_page  # noqa: E402

FAILS: list[str] = []
SID = "X-UIT" + str(int(__import__("time").time()) % 10000)


def api_login(user: str, pw: str) -> dict[str, str]:
    c = httpx.Client(base_url=BASE, timeout=30)
    r = c.post("/api/v1/auth/login", json={"username": user, "password": pw})
    return {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ✅ {label}")
    else:
        print(f"  ❌ {label} {detail}")
        FAILS.append(label)


def cleanup() -> None:
    admin = api_login("admin01", "Admin@12345")
    with httpx.Client(base_url=BASE, timeout=30) as c:
        c.delete(f"/api/v1/admin/scenarios/{SID}", headers=admin)
    print(f"  已清理 {SID}")


def login_ui(cdp, user: str) -> None:
    cdp.eval("localStorage.clear();localStorage.setItem('knock.tourDone','1')")
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


def set_input(cdp, selector: str, value: str, index: int = 0) -> bool:
    """给第 index 个匹配的输入框赋值并触发 React onChange。"""
    return bool(cdp.eval(
        """(() => {
          const els = [...document.querySelectorAll('%s')];
          const el = els[%d];
          if (!el) return false;
          const proto = el.tagName === 'TEXTAREA'
            ? window.HTMLTextAreaElement.prototype
            : (el.tagName === 'SELECT'
               ? window.HTMLSelectElement.prototype
               : window.HTMLInputElement.prototype);
          const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
          setter.call(el, '%s');
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        })()""" % (selector, index, value)
    ))


def main() -> int:
    proc = launch_chrome(window_size="1440,1200")
    try:
        cdp = open_page(BASE, window_size="1440,1200")

        print("=== 1. 教师进入案例管理 ===")
        login_ui(cdp, "teacher01")
        cdp.eval("location.hash = '#/teacher'")
        time.sleep(5)
        ok = cdp.eval(
            """(() => {
              const b = [...document.querySelectorAll('button.wb-tab')].find(x => {
                const c = x.cloneNode(true);
                c.querySelectorAll('.no').forEach(n => n.remove());
                return c.textContent.trim() === '案例管理';
              });
              if (!b) return false;
              b.click();
              return true;
            })()"""
        )
        check("找到「案例管理」页签", ok)
        time.sleep(3)

        rows = cdp.eval(
            """(() => [...document.querySelectorAll('.wb-row')].map(r => r.innerText))()"""
        ) or []
        print(f"  列表行数: {len(rows)}")
        check("案例列表已渲染", len(rows) >= 12, f"实际 {len(rows)}")

        builtin_rows = [r for r in rows if "内置" in r]
        check("内置案例标记为「内置」", len(builtin_rows) > 0)
        check(
            "内置案例显示「只读」而不是编辑按钮",
            any("只读" in r for r in builtin_rows),
            f"内置行示例: {builtin_rows[0][:60] if builtin_rows else '-'}",
        )

        print("\n=== 2. 用表单新建案例 ===")
        # 表单输入框顺序：ID、名称、年龄、类型
        set_input(cdp, '.wb-form input.wb-input', SID, 0)
        set_input(cdp, '.wb-form input.wb-input', "界面建的·赵姐", 1)
        set_input(cdp, '.wb-form input.wb-input', "41", 2)
        set_input(cdp, '.wb-form input.wb-input', "单亲母亲", 3)
        time.sleep(0.3)
        # 两块 textarea：brief、system_prompt
        set_input(cdp, '.wb-form textarea.wb-input', "离婚后独自抚养两个孩子，打两份工，担心孩子学坏。", 0)
        set_input(cdp, '.wb-form textarea.wb-input', "你扮演 41 岁单亲母亲赵姐，语气急、常打断，最担心孩子。", 1)
        time.sleep(0.3)
        clicked = cdp.eval(
            """(() => {
              const b = [...document.querySelectorAll('button.btn-primary')]
                .find(x => x.textContent.trim() === '保存');
              if (!b) return false;
              b.click();
              return true;
            })()"""
        )
        check("点到了保存按钮", clicked)
        time.sleep(4)

        body = cdp.eval("document.body.innerText") or ""
        check("出现保存成功提示", "已保存" in body, body[:80])
        rows2 = cdp.eval(
            """(() => [...document.querySelectorAll('.wb-row')].map(r => r.innerText))()"""
        ) or []
        check("新案例出现在列表", any(SID in r for r in rows2), f"共 {len(rows2)} 行")

        print("\n=== 3. 学生端可见 ===")
        login_ui(cdp, "student01")
        cdp.eval("location.hash = '#/cases'")
        time.sleep(4)
        cases = cdp.eval(
            """(() => [...document.querySelectorAll('.case')].map(c => c.innerText))()"""
        ) or []
        print(f"  选角卡数: {len(cases)}")
        check("学生选角页出现新案例", any("赵姐" in c for c in cases), f"共 {len(cases)} 张")

        print("\n=== 4. 教师建的角色能真正进去训练 ===")
        # 选中新卡片 → 点开始面谈
        clicked = cdp.eval(
            """(() => {
              const cards = [...document.querySelectorAll('.case')];
              const card = cards.find(c => c.innerText.includes('赵姐'));
              if (!card) return 'no-card';
              card.click();
              return 'ok';
            })()"""
        )
        check("选中教师新建的案例卡", clicked == 'ok', str(clicked))
        time.sleep(1)
        cdp.eval(
            """(() => {
              const b = [...document.querySelectorAll('button')]
                .find(x => x.textContent.includes('开始面谈'));
              if (b) b.click();
            })()"""
        )
        time.sleep(6)
        head = cdp.eval(
            """(() => {
              const el = document.querySelector('.casefile');
              return el ? el.innerText.slice(0, 80) : '';
            })()"""
        ) or ""
        print(f"  训练页头: {head!r}")
        check("进入了训练页（未被路由守卫拦下）", bool(head), "页头为空")
        check("训练页显示了新角色信息", "赵姐" in head or "单亲" in head, head[:60])

        cdp.shot(SHOTS / "teacher_scenario_manager.png")
        cdp.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()
        cleanup()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 项未通过：{FAILS}")
        return 1
    print("✅ 教师端案例管理界面端到端通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
