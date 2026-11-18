"""性能基线测量。

目前 README 里的"首屏约 130KB（gzip）"是从构建产物推算的，
没有实测数据。这个脚本测两类真实数字：

一 前端首屏
- 首屏实际传输字节数（含压缩后大小）
- DOMContentLoaded / load 时间
- FCP / LCP（浏览器原生 PerformanceObserver）
- 请求数量

二 接口延迟
- 关键接口的 p50 / p95 / max（本地单机，非并发压测）

重要说明：这些是**单机本地**数字，不是并发压测结果。并发能力未测试，
报告里不得把本地延迟当成容量结论。
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from ui_smoke import BASE, http_json, launch_chrome, open_page  # noqa: E402

# 关键接口（不含需要 AI 的路径）
ENDPOINTS = [
    ("登录", "POST", "/api/v1/auth/login", None),
    ("案例列表", "GET", "/api/v1/scenarios", None),
    ("知识卡", "GET", "/api/v1/knowledge/cards", None),
    ("个人统计", "GET", "/api/v1/stats/me", "student"),
    ("教师班级看板", "GET", "/api/v1/teacher/stats", "teacher"),
    ("平台概览", "GET", "/api/v1/admin/overview", "admin"),
]

PW = {"student": ("student01", "Student@12345"),
      "teacher": ("teacher01", "Teacher@12345"),
      "admin": ("admin01", "Admin@12345")}


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((len(ordered) - 1) * p)))
    return ordered[idx]


def bench_api() -> tuple[list[tuple[str, int, float, float, float]], str]:
    c = httpx.Client(base_url=BASE, timeout=30)
    tokens: dict[str, str] = {}
    for who, (user, pwd) in PW.items():
        r = c.post("/api/v1/auth/login", json={"username": user, "password": pwd})
        tokens[who] = r.json()["data"]["tokens"]["access_token"]

    rows = []
    for label, method, path, who in ENDPOINTS:
        headers = {}
        if who:
            headers["Authorization"] = f"Bearer {tokens[who]}"
        payload = PW["student"] and None
        if method == "POST" and "login" in path:
            payload = {"username": PW["student"][0], "password": PW["student"][1]}

        samples: list[float] = []
        for _ in range(12):
            t0 = time.perf_counter()
            if method == "GET":
                resp = c.get(path, headers=headers)
            else:
                resp = c.post(path, headers=headers, json=payload)
            samples.append((time.perf_counter() - t0) * 1000)
            if resp.status_code >= 400:
                samples = []
                break
        # 前 2 次是冷启动（连接建立、JIT），丢弃
        warm = samples[2:] if len(samples) > 4 else samples
        rows.append((
            label,
            len(warm),
            round(pct(warm, 0.50), 1),
            round(pct(warm, 0.95), 1),
            round(max(warm) if warm else 0, 1),
        ))
    return rows, ""


def bench_frontend() -> dict[str, object] | None:
    proc = launch_chrome(window_size="1440,900")
    try:
        cdp = open_page(BASE, window_size="1440,900")

        # 用 Resource Timing 统计首屏真实传输量
        metrics = cdp.eval(
            """(() => {
              const nav = performance.getEntriesByType('navigation')[0] || {};
              const res = performance.getEntriesByType('resource');
              let transferred = 0, encoded = 0, decoded = 0;
              for (const r of res) {
                transferred += r.transferSize || 0;
                encoded += r.encodedBodySize || 0;
                decoded += r.decodedBodySize || 0;
              }
              return {
                requests: res.length,
                transferred_kb: Math.round(transferred / 1024),
                decoded_kb: Math.round(decoded / 1024),
                domContentLoaded: Math.round(nav.domContentLoadedEventEnd || 0),
                loadEvent: Math.round(nav.loadEventEnd || 0),
                fcp: (performance.getEntriesByName('first-contentful-paint')[0] || {}).startTime || null,
              };
            })()"""
        )

        # LCP 需要 observer，单独取
        lcp = cdp.eval(
            """(() => new Promise(resolve => {
              try {
                const po = new PerformanceObserver((list) => {
                  const e = list.getEntries();
                  resolve(Math.round(e[e.length - 1].startTime));
                });
                po.observe({ type: 'largest-contentful-paint', buffered: true });
                setTimeout(() => resolve(null), 2500);
              } catch (e) { resolve(null); }
            }))()"""
        )

        if metrics:
            metrics["lcp"] = lcp
            # 图表库是否在首屏加载（懒加载验证）
            metrics["echarts_on_first_load"] = cdp.eval(
                "performance.getEntriesByType('resource')"
                ".some(r => r.name.includes('charts-'))"
            )
        cdp.close()
        return metrics
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()


def main() -> int:
    print("=" * 62)
    print(" 性能基线测量（单机本地，非并发压测）")
    print("=" * 62)

    print("\n【一】前端首屏")
    fe = bench_frontend()
    if not fe:
        print("  测量失败")
        return 1
    print(f"  请求数            {fe['requests']}")
    print(f"  传输量(压缩后)     {fe['transferred_kb']} KB")
    print(f"  解压后             {fe['decoded_kb']} KB")
    print(f"  DOMContentLoaded  {fe['domContentLoaded']} ms")
    print(f"  load 事件          {fe['loadEvent']} ms")
    fcp = fe.get("fcp")
    print(f"  FCP                {round(fcp) if fcp else '—'} ms")
    print(f"  LCP                {fe.get('lcp') or '—'} ms")
    charts = fe.get("echarts_on_first_load")
    print(f"  首屏加载图表库      {'是（懒加载失效！）' if charts else '否 ✓'}")

    print("\n【二】接口延迟（单位 ms，丢弃前 2 次冷启动）")
    print(f"  {'接口':<16}{'样本':>5}{'p50':>9}{'p95':>9}{'max':>9}")
    rows, _ = bench_api()
    for label, n, p50, p95, mx in rows:
        print(f"  {label:<16}{n:>5}{p50:>9}{p95:>9}{mx:>9}")

    print("\n【说明】")
    print("  · 本机单用户顺序请求，不是并发压测，不能作为容量结论")
    print("  · 首屏传输量取 Resource Timing 实测，非构建产物推算")

    # 结果写入文件供文档引用
    out = Path(__file__).parent / "qa" / "perf-baseline.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "性能基线测量结果（单机本地，非并发压测）",
        f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "前端首屏：",
        f"  请求数 {fe['requests']}",
        f"  传输量(压缩) {fe['transferred_kb']} KB / 解压后 {fe['decoded_kb']} KB",
        f"  DOMContentLoaded {fe['domContentLoaded']} ms / load {fe['loadEvent']} ms",
        f"  FCP {round(fcp) if fcp else '—'} ms / LCP {fe.get('lcp') or '—'} ms",
        f"  首屏是否加载图表库：{'是' if charts else '否'}",
        "",
        "接口延迟(ms)：",
    ]
    for label, n, p50, p95, mx in rows:
        lines.append(f"  {label}: n={n} p50={p50} p95={p95} max={mx}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n结果已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
