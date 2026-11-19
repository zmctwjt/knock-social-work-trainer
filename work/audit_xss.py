"""存储型 XSS 的浏览器端验证。

服务端层已由 tests/test_input_security.py 验证（原样保存 + 声明 JSON）。
这里验证**真正的防线**：载荷被渲染到页面时，是否会执行。

做法
1. 用管理员 API 写入含 `<script>` 与 `onerror` 的知识卡；
2. 打开知识库页面，检查：
   - 页面上是否有执行痕迹（预置的 window.__xss_fired 标记）
   - DOM 里是否存在被注入的 script 标签
   - 载荷是否以纯文本展示（innerText 里能看到源码）
3. 再在教师点评里注入一次，验证成长中心展示同样安全。

React 默认把字符串作为文本节点插入，所以预期全部安全；
这个脚本的价值是**把"预期"变成"验证"**，防止以后有人用
dangerouslySetInnerHTML 引入漏洞。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from ui_smoke import BASE, http_json, launch_chrome, open_page  # noqa: E402

FAILS: list[str] = []
#: 能被 innerText 看到的载荷；同时尝试触发 alert/错误处理器
PAYLOAD = "<script>window.__xss_fired=1</script><img src=x onerror=\"window.__xss_fired=2\">"


def seed_payload() -> bool:
    """用管理员 API 写入含载荷的技巧卡。"""
    c = httpx.Client(base_url=BASE, timeout=25)
    token = c.post(
        "/api/v1/auth/login",
        json={"username": "admin01", "password": "Admin@12345"},
    ).json()["data"]["tokens"]["access_token"]
    r = c.post(
        "/api/v1/admin/cards",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "id": "T-XXS",
            "title": PAYLOAD,
            "category": "技巧",
            "summary": PAYLOAD,
            "content": PAYLOAD,
        },
    )
    print(f"  写入载荷技巧卡: {r.status_code}")
    return r.status_code == 200


def login(cdp, user: str) -> None:
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


def check_page(cdp, label: str, keyword: str) -> None:
    """检查当前页面的 XSS 执行痕迹。"""
    state = cdp.eval(
        """(() => {
          const scripts = [...document.querySelectorAll('script')]
            .filter(s => (s.textContent || '').includes('%s'));
          return {
            fired: window.__xss_fired || null,
            injectedScripts: scripts.length,
            bodyHasPayload: document.body.innerText.includes('__xss_fired'),
            imgCount: document.querySelectorAll('img[src="x"]').length,
          };
        })()""" % keyword
    )
    print(f"  [{label}] 执行标记={state['fired']} 注入script={state['injectedScripts']} "
          f"文本可见={state['bodyHasPayload']} 注入img={state['imgCount']}")

    if state["fired"]:
        FAILS.append(f"{label}: XSS 载荷被执行了（window.__xss_fired={state['fired']}）")
    if state["injectedScripts"] > 0:
        FAILS.append(f"{label}: DOM 里出现注入的 script 标签")
    if not state["bodyHasPayload"]:
        FAILS.append(f"{label}: 载荷没有作为文本展示（可能被静默丢弃，数据保真受损）")


def main() -> int:
    print("=== 1. 写入 XSS 载荷 ===")
    if not seed_payload():
        print("  写入失败，跳过后续")
        return 1

    proc = launch_chrome(window_size="1440,1200")
    try:
        cdp = open_page(BASE, window_size="1440,1200")
        # 在页面加载前埋执行标记的检测（React 渲染后读 window）
        cdp.eval("window.__xss_fired = null")

        print("\n=== 2. 知识库（学生视角）===")
        login(cdp, "student01")
        cdp.eval("location.hash = '#/knowledge'")
        time.sleep(4)
        # 搜索框输入 T-XXS 定位到这张卡
        cdp.eval(
            """(() => {
              const i = document.querySelector('.kb-search input');
              if (!i) return;
              const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
              setter.call(i, '__xss_fired');
              i.dispatchEvent(new Event('input', { bubbles: true }));
            })()"""
        )
        time.sleep(2)
        check_page(cdp, "知识库", "__xss_fired")

        # 教师端「内容查阅」已下线（与学员端知识库重复）。
        # 改在管理端「内容维护」验证同一份数据库卡片的渲染安全性。
        print("\n=== 3. 管理端内容维护 ===")
        login(cdp, "admin01")
        time.sleep(2)
        ok = cdp.eval(
            """(() => {
              const b = [...document.querySelectorAll('button.wb-tab')].find(x => {
                const c = x.cloneNode(true);
                c.querySelectorAll('.no').forEach(n => n.remove());
                return c.textContent.trim() === '内容维护';
              });
              if (!b) return false;
              b.click();
              return true;
            })()"""
        )
        time.sleep(3)
        print(f"  切到内容维护: {ok}")
        check_page(cdp, "管理端", "__xss_fired")

        cdp.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 项：")
        for f in FAILS:
            print("   -", f)
        return 1
    print("✅ 存储型 XSS 未被执行，载荷以纯文本展示")
    return 0


if __name__ == "__main__":
    sys.exit(main())
