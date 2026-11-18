"""知识库检索验收（任务书要求「按案例与关键词检索」）。

检查：
1. 关键词检索生效，命中数正确；
2. 按案例筛选生效，且与关键词可叠加；
3. 清空筛选恢复全部；
4. 六维筛选生效；
5. 无横向溢出（移动端）。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ui_smoke import CDP, CHROME, PORT, PROFILE, SHOTS, http_json, launch_chrome, open_page  # noqa: E402

BASE = "http://127.0.0.1:8000"
FAILS: list[str] = []


def count_cards(cdp: CDP) -> int:
    return int(cdp.eval("document.querySelectorAll('.kcard').length") or 0)


def set_keyword(cdp: CDP, text: str) -> None:
    cdp.eval(
        """(() => {
          const i = document.querySelector('.kb-search input');
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
          setter.call(i, '%s');
          i.dispatchEvent(new Event('input', { bubbles: true }));
        })()""" % text
    )
    time.sleep(1.0)


def set_select(cdp: CDP, index: int, value: str) -> None:
    cdp.eval(
        """(() => {
          const s = document.querySelectorAll('.kb-filters select')[%d];
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLSelectElement.prototype, 'value').set;
          setter.call(s, '%s');
          s.dispatchEvent(new Event('change', { bubbles: true }));
        })()""" % (index, value)
    )
    time.sleep(1.0)


def main() -> int:
    proc = launch_chrome(window_size="1440,1300")
    try:
        cdp = open_page(BASE, window_size="1440,1300")
        time.sleep(3)
        cdp.eval("localStorage.setItem('knock.tourDone','1')")
        cdp.eval(f"location.href='{BASE}/#/knowledge'")
        time.sleep(1)
        cdp.eval("location.reload()")
        time.sleep(5)

        print("\n=== 初始状态 ===")
        base = count_cards(cdp)
        print(f"  技巧卡总数: {base}")
        if base < 19:
            FAILS.append(f"初始卡片数异常: {base}")

        print("\n=== 关键词检索 ===")
        set_keyword(cdp, "同感")
        kw_count = count_cards(cdp)
        print(f"  搜「同感」命中: {kw_count}")
        if not (0 < kw_count <= base):
            FAILS.append(f"关键词检索结果异常: {kw_count}")

        print("\n=== 按案例检索（任务书要求）===")
        set_keyword(cdp, "")
        # 选中第一个真实案例（跳过"全部案例"）
        first_case = cdp.eval(
            "document.querySelectorAll('.kb-filters select')[0].options[1].value"
        )
        set_select(cdp, 0, first_case)
        case_count = count_cards(cdp)
        print(f"  案例 {first_case} 命中: {case_count}")
        if case_count >= base:
            FAILS.append("按案例筛选没有起作用")
        # 每张卡都应显示"适用案例"
        has_case_hint = cdp.eval(
            "document.querySelectorAll('.kcard-case').length"
        )
        print(f"  显示「适用案例」的卡片: {has_case_hint}")
        if has_case_hint != case_count:
            FAILS.append(f"适用案例提示数量不符: {has_case_hint} vs {case_count}")

        print("\n=== 案例 + 关键词叠加 ===")
        set_keyword(cdp, "提问")
        combo = count_cards(cdp)
        print(f"  叠加后命中: {combo}")
        if combo > case_count:
            FAILS.append("叠加筛选后结果反而变多")

        print("\n=== 清空筛选 ===")
        cdp.eval(
            """(() => {
              const b = document.querySelector('.kb-reset');
              if (b) b.click();
            })()"""
        )
        time.sleep(1.2)
        after_reset = count_cards(cdp)
        print(f"  清空后: {after_reset}")
        if after_reset != base:
            FAILS.append(f"清空筛选未恢复全部: {after_reset} != {base}")

        print("\n=== 六维筛选 ===")
        set_select(cdp, 1, "empathy")
        dim_count = count_cards(cdp)
        print(f"  同感维度命中: {dim_count}")
        if not (0 < dim_count <= base):
            FAILS.append(f"维度筛选异常: {dim_count}")

        print("\n=== 移动端无溢出 ===")
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            width=390, height=844, deviceScaleFactor=1, mobile=True,
        )
        time.sleep(1.5)
        overflow = cdp.eval(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        print(f"  横向溢出: {overflow}px")
        if (overflow or 0) > 2:
            FAILS.append(f"移动端横向溢出 {overflow}px")

        cdp.shot(SHOTS / "knowledge_filters.png")
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
    print("✅ 知识库按案例 + 关键词检索全部符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())
