"""并发压测：给出一份可复现的容量数据。

不引入 locust/k6 之类的依赖（本机约定不额外装软件），
用 httpx + asyncio 自己压。测量对象是真实运行的服务。

测两类场景：
1. **只读接口**（案例列表、知识卡、就绪检查）—— 高频、轻量，
   代表"打开页面"这类请求；
2. **登录**—— 最重的一段（Argon2id 哈希），代表并发登录，
   也最能暴露 CPU 瓶颈。

不测 AI 接口：有外部配额，压测没有意义且会消耗调用额度。

输出 p50 / p90 / p95 / p99 与错误率，写入 work/qa/loadtest.txt。
"""
from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "qa" / "loadtest.txt"

#: 并发档位：(并发数, 每档总请求数)
LEVELS = [(10, 200), (30, 300), (50, 500)]


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((p / 100) * (len(ordered) - 1))))
    return ordered[idx]


async def hammer(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    total: int,
    concurrency: int,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
) -> tuple[list[float], int, dict[int, int]]:
    """跑 total 次请求，并发上限 concurrency，返回延迟列表与错误数。"""
    latencies: list[float] = []
    errors = 0
    status_count: dict[int, int] = {}
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()

    async def one() -> None:
        nonlocal errors
        async with sem:
            t0 = time.perf_counter()
            try:
                r = await client.request(method, path, headers=headers, json=body)
                ms = (time.perf_counter() - t0) * 1000
                async with lock:
                    latencies.append(ms)
                    status_count[r.status_code] = status_count.get(r.status_code, 0) + 1
                    if r.status_code >= 500:
                        errors += 1
            except Exception:  # noqa: BLE001
                async with lock:
                    errors += 1
                    status_count[-1] = status_count.get(-1, 0) + 1

    t_start = time.perf_counter()
    await asyncio.gather(*[one() for _ in range(total)])
    elapsed = time.perf_counter() - t_start
    print(f"    用时 {elapsed:.1f}s，吞吐 {total / elapsed:.0f} req/s", end="")
    return latencies, errors, status_count


async def main() -> int:
    lines: list[str] = []
    fails: list[str] = []

    def emit(text: str = "") -> None:
        print(text)
        lines.append(text)

    limits = httpx.Limits(max_connections=200, max_keepalive_connections=100)
    async with httpx.AsyncClient(base_url=BASE, timeout=60, limits=limits) as c:
        try:
            ready = (await c.get("/readyz")).json()["data"]
        except Exception as exc:  # noqa: BLE001
            print(f"服务不可达：{exc}")
            return 1

        emit("=" * 68)
        emit(" 并发压测")
        emit(f" 目标 {BASE} · 数据库 {ready['checks'][0]['detail']} · "
             f"缓存 {ready['checks'][1]['detail']}")
        emit(f" 时间 {time.strftime('%Y-%m-%d %H:%M:%S')}")
        emit("=" * 68)

        # 先登录拿 token，供后续鉴权请求复用
        login_body = {"username": "student01", "password": "Student@12345"}
        token = (await c.post("/api/v1/auth/login", json=login_body)).json()["data"]["tokens"][
            "access_token"
        ]
        auth_h = {"Authorization": f"Bearer {token}"}

        for concurrency, total in LEVELS:
            emit("")
            emit(f"── 并发 {concurrency}，共 {total} 请求 ──")

            # ① 轻量只读：就绪检查（不查库、不打鉴权，纯框架路径）
            print(f"  /readyz            ", end="")
            lat, err, codes = await hammer(c, "GET", "/readyz", total, concurrency)
            emit(f"    p50={pct(lat, 50):.0f}ms p95={pct(lat, 95):.0f}ms "
                 f"p99={pct(lat, 99):.0f}ms 错误={err}")
            if err:
                fails.append(f"/readyz 并发 {concurrency} 有 {err} 个 5xx")
            if pct(lat, 95) > 1500:
                fails.append(f"/readyz p95 {pct(lat, 95):.0f}ms 超过 1500ms")

            # ② 只读 + 查库 + 鉴权：案例列表
            print(f"  /scenarios         ", end="")
            lat, err, codes = await hammer(
                c, "GET", "/api/v1/scenarios", total, concurrency, headers=auth_h
            )
            emit(f"    p50={pct(lat, 50):.0f}ms p95={pct(lat, 95):.0f}ms "
                 f"p99={pct(lat, 99):.0f}ms 错误={err}")
            if err:
                fails.append(f"/scenarios 并发 {concurrency} 有 {err} 个 5xx")
            if pct(lat, 95) > 2000:
                fails.append(f"/scenarios p95 {pct(lat, 95):.0f}ms 超过 2000ms")

            # ③ 最重的登录（Argon2id）：并发数减半，避免把 CPU 打满影响后续档位
            print(f"  /auth/login        ", end="")
            lat, err, codes = await hammer(
                c, "POST", "/api/v1/auth/login",
                max(20, total // 4), max(4, concurrency // 2), body=login_body,
            )
            emit(f"    p50={pct(lat, 50):.0f}ms p95={pct(lat, 95):.0f}ms "
                 f"p99={pct(lat, 99):.0f}ms 错误={err}")
            # 登录被限流是预期行为（429），只把 5xx 记为失败
            if err:
                fails.append(f"/auth/login 并发 {concurrency} 有 {err} 个 5xx")

    emit("")
    emit("=" * 68)
    emit(" 说明")
    emit(" - 错误数只统计 5xx 与连接异常；429 限流属预期保护，不计失败。")
    emit(" - 单机、本机回环，未跨网络；真实部署应把应用与数据库分开测。")
    emit(" - AI 接口有外部配额，未纳入压测。")
    emit("=" * 68)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n结果已写入 {OUT}")

    if fails:
        print("\n❌ 未达预期：")
        for f in fails:
            print("   -", f)
        return 1
    print("\n✅ 各并发档位均无 5xx，p95 在阈值内")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
