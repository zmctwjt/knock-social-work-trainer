"""响应压缩测试。

起因：实测发现后端此前**完全没有 gzip**——首屏 9 个请求传输 753 KB，
与解压后 750 KB 几乎相同（等于没压）。加上 GZipMiddleware 后实测降到
216 KB，FCP 从 320 ms 降到 248 ms。

这组测试防止中间件被误删或被顺序调整导致失效。

关于 minimum_size 的实测结论
本项目的响应以流式发送（`Transfer-Encoding: chunked`），Starlette 的
GZipMiddleware 只在**非流式**分支里判断 `len(body) < minimum_size`，
流式响应一律压缩。因此 150 字节的 /healthz 也会被压（压完还更小）。
这不是缺陷，是中间件既定行为；测试不应假设"小响应一定不压缩"。
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_response_is_gzipped_when_accepted(api):
    """声明接受 gzip 时，响应应带 Content-Encoding: gzip。"""
    application, client = await api()
    resp = await client.get(
        "/api/v1/scenarios",
        headers={"Accept-Encoding": "gzip"},
    )
    assert resp.status_code == 200
    encoding = resp.headers.get("content-encoding", "")
    assert "gzip" in encoding.lower(), (
        f"响应未被压缩（content-encoding={encoding or '无'}），"
        "检查 GZipMiddleware 是否被移除或顺序被改到最内层"
    )


@pytest.mark.asyncio
async def test_no_gzip_when_client_refuses(api):
    """客户端不接受 gzip 时不得压缩——否则客户端无法解码。"""
    application, client = await api()
    resp = await client.get(
        "/api/v1/scenarios",
        headers={"Accept-Encoding": "identity"},
    )
    assert resp.status_code == 200
    assert "gzip" not in resp.headers.get("content-encoding", "").lower(), (
        "客户端声明 identity 却收到了 gzip"
    )


@pytest.mark.asyncio
async def test_compressed_body_decodes_correctly(api):
    """压缩必须对调用方透明：解压后内容与未压缩一致。

    这是压缩最关键的契约——压坏了比不压更糟。
    """
    application, client = await api()
    plain = await client.get(
        "/api/v1/scenarios", headers={"Accept-Encoding": "identity"}
    )
    packed = await client.get(
        "/api/v1/scenarios", headers={"Accept-Encoding": "gzip"}
    )
    assert plain.status_code == packed.status_code == 200

    # httpx 会自动解压，所以这里比较的是解压后的语义内容
    a = plain.json()
    b = packed.json()
    # request_id 每次不同，比对业务字段
    assert a["code"] == b["code"] == 0
    assert [x["id"] for x in a["data"]["items"]] == [
        x["id"] for x in b["data"]["items"]
    ]


@pytest.mark.asyncio
async def test_vary_header_present(api):
    """压缩必须带 Vary: Accept-Encoding，否则中间缓存会串味
    （把压缩版发给不支持 gzip 的客户端）。"""
    application, client = await api()
    resp = await client.get(
        "/api/v1/scenarios", headers={"Accept-Encoding": "gzip"}
    )
    vary = resp.headers.get("vary", "").lower()
    assert "accept-encoding" in vary, f"缺少 Vary: Accept-Encoding（实际 vary={vary!r}）"
