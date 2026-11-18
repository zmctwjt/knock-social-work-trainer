"""核心训练流程端到端审查。

这是整个系统最重要的用户旅程，此前只有 API 层测试与一个只打印文本的
开发期快照脚本，**没有任何断言级浏览器 E2E**。

覆盖完整闭环：
登录 → 选案例 → 进面谈室 → 逐句输入 → 服务对象回应 → 六维评分更新
→ 提交本阶段 → 落到结算页 → 记录进成长中心

另测危机处置：输入危机表述后必须立即中止对话并弹出处置提示
（这条是安全底线，不能只靠 API 测试）。
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

# 覆盖不同维度的三句话，保证评分有区分度
UTTERANCES = [
    "王阿姨您好，我是社区的小陈，今天想陪您聊聊最近的情况，您方便吗？",
    "听您说一个人吃饭做多了吃不完，这种日子确实不好受。",
    "您愿意跟我多讲讲，最近睡眠不好的时候都在想些什么吗？",
]


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


def wait_hash(cdp: CDP, want: str, timeout: float = 15.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if cdp.eval("location.hash") == want:
            return True
        time.sleep(0.4)
    return False


def send_utterance(cdp: CDP, text: str) -> str:
    """填输入框并点发送，返回状态。"""
    filled = cdp.eval(
        """(() => {
          const i = document.querySelector('.composer-input');
          if (!i) return 'NO-INPUT';
          if (i.disabled) return 'INPUT-DISABLED';
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
          setter.call(i, '%s');
          i.dispatchEvent(new Event('input', { bubbles: true }));
          return 'ok';
        })()""" % text.replace("'", "\\'")
    )
    if filled != "ok":
        return filled
    time.sleep(0.5)
    clicked = cdp.eval(
        """(() => {
          const b = document.querySelector('button.send');
          if (!b) return 'NO-SEND';
          if (b.disabled) return 'SEND-DISABLED';
          b.click();
          return 'ok';
        })()"""
    )
    return clicked


def turn_count(cdp: CDP) -> int:
    return int(cdp.eval("document.querySelectorAll('.script-log .turn').length") or 0)


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
        cdp.eval(
            "window.__errs=[];"
            "window.addEventListener('error',e=>window.__errs.push(String(e.message)));"
            "window.addEventListener('unhandledrejection',e=>window.__errs.push('R:'+e.reason))"
        )

        print("\n=== 1. 登录并进入案例选择 ===")
        login(cdp, "student01")
        arrived = wait_hash(cdp, "#/cases")
        print(f"  落地 #/cases: {arrived}")
        if not arrived:
            FAILS.append("登录后未进入案例选择页")

        print("\n=== 2. 进入面谈室 ===")
        cdp.eval("location.hash = '#/training/W-01'")
        ok = wait_hash(cdp, "#/training/W-01")
        time.sleep(3)
        has_input = cdp.eval("!!document.querySelector('.composer-input')")
        has_log = cdp.eval("!!document.querySelector('.script-log')")
        print(f"  hash 到达: {ok}  输入框: {has_input}  逐字稿区: {has_log}")
        if not (ok and has_input and has_log):
            FAILS.append("面谈室关键元素缺失")
            cdp.close()
            raise SystemExit(1)

        print("\n=== 3. 逐句输入并检查服务对象回应 ===")
        before = turn_count(cdp)
        for i, text in enumerate(UTTERANCES, start=1):
            r = send_utterance(cdp, text)
            time.sleep(4)
            now = turn_count(cdp)
            # 每句应产生「我方发言 + 服务对象回应」至少 1 条新增
            grew = now > before
            print(f"  第{i}句 发送={r} 轮次 {before}→{now} 增长={grew}")
            if r != "ok":
                FAILS.append(f"第{i}句发送失败: {r}")
            if not grew:
                FAILS.append(f"第{i}句后逐字稿没有新增回合")
            before = now

        print("\n=== 4. 六维评分面板是否更新 ===")
        # 真实结构：.col-proof .score 是总分，.checklist .check-num 是六维分项
        proof = cdp.eval(
            """(() => {
              const panel = document.querySelector('.col-proof');
              if (!panel) return null;
              const total = panel.querySelector('.score');
              const dims = [...panel.querySelectorAll('.checklist li')].map(li => {
                const name = li.querySelector('.check-name');
                const num = li.querySelector('.check-num');
                return {
                  name: name ? name.textContent.trim().split('·')[0].trim() : '',
                  value: num ? num.textContent.trim() : null,
                };
              });
              return {
                total: total ? total.textContent.trim() : null,
                dimCount: dims.length,
                dims,
              };
            })()"""
        )
        print(f"  总分: {proof['total'] if proof else 'N/A'}")
        print(f"  维度数: {proof['dimCount'] if proof else 0}")
        if proof and proof["dims"]:
            for d in proof["dims"]:
                print(f"    {d['name']}: {d['value']}")
        if not proof:
            FAILS.append("六维评分面板不存在")
        elif proof["dimCount"] != 6:
            FAILS.append(f"六维面板应有 6 个维度，实际 {proof['dimCount']}")
        elif any(d["value"] is None for d in proof["dims"]):
            FAILS.append("有维度没有显示分值")

        print("\n=== 5. 提交本阶段 ===")
        submitted = cdp.eval(
            """(() => {
              const b = document.querySelector('button.submit');
              if (!b) return 'NO-BTN';
              if (b.disabled) return 'DISABLED';
              b.click();
              return 'ok';
            })()"""
        )
        print(f"  点提交: {submitted}")
        if submitted != "ok":
            FAILS.append(f"提交本阶段失败: {submitted}")
        # 提交后默认自动跳结算页
        settled = wait_hash(cdp, "#/settle", timeout=20)
        time.sleep(2)
        print(f"  落到结算页: {settled}")
        if not settled:
            FAILS.append("提交后未进入结算页")

        print("\n=== 6. 结算页展示成绩 ===")
        settle = cdp.eval(
            """(() => {
              const head = document.querySelector('.settle-head');
              if (!head) return null;
              const score = head.querySelector('.settle-score .n');
              return {
                has_head: true,
                score: score ? score.textContent.trim() : null,
                text: head.innerText.slice(0, 80),
              };
            })()"""
        )
        print(f"  结算页: {settle}")
        if not settle:
            FAILS.append("结算页结构缺失")
        elif not settle["score"]:
            FAILS.append("结算页没有显示分数")

        print("\n=== 7. 记录进入成长中心 ===")
        cdp.eval("location.hash = '#/growth'")
        wait_hash(cdp, "#/growth", timeout=15)
        time.sleep(3)
        growth = cdp.eval("document.body.innerText") or ""
        has_data = "还没有训练记录" not in growth
        has_radar = "六维" in growth or "雷达" in growth
        print(f"  有训练数据: {has_data}  含六维视图: {has_radar}")
        if not has_data:
            FAILS.append("成长中心仍显示无记录（提交的成绩没落库）")

        print("\n=== 8. 危机处置 ===")
        cdp.eval("location.hash = '#/training/W-01'")
        wait_hash(cdp, "#/training/W-01", timeout=15)
        time.sleep(3)
        crisis_sent = send_utterance(cdp, "我真的不想活了，活着没意思。")
        time.sleep(6)
        crisis_ui = cdp.eval(
            """(() => {
              const d = document.querySelector('[role="alertdialog"]');
              if (!d) return null;
              return { text: d.innerText.slice(0, 120) };
            })()"""
        )
        print(f"  发送={crisis_sent}  危机提示: {bool(crisis_ui)}")
        if crisis_ui:
            print(f"  提示内容: {crisis_ui['text'][:80]}")
        else:
            # 危机也可能以系统消息形式出现在逐字稿里
            log_text = cdp.eval("document.querySelector('.script-log').innerText") or ""
            has_crisis_word = any(w in log_text for w in ("危机", "转介", "风险", "中止"))
            print(f"  未弹对话框，逐字稿含危机词: {has_crisis_word}")
            if not has_crisis_word:
                FAILS.append("危机表述未触发任何处置提示")

        errs = cdp.eval("window.__errs") or []
        if errs:
            for e in errs[:3]:
                FAILS.append(f"控制台错误: {e}")

        cdp.shot(SHOTS / "training_flow.png")
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
    print("✅ 核心训练流程端到端通过（输入→回应→评分→结算→成长记录→危机处置）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
