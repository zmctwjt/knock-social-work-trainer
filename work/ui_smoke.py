"""用 Chrome DevTools Protocol 验证前端训练流程（本地 localStorage 账号 + 规则模式后端）。

流程：启动无头 Chrome → 打开 /login → 注入演示账号 → 进入 /training/W-01 →
输入一句社工发言并发送 → 截图两帧 → 打印页面片段与网络失败信息。

用法：python work/ui_smoke.py
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import websocket

# Chrome 与端口均可用环境变量覆盖，便于在 Linux/CI 上复用同一套审查脚本。
# CI 里 Chrome 通常在 /usr/bin/google-chrome，本地 Windows 在 Program Files。
import os
import shutil as _shutil

CHROME = (
    os.getenv("CHROME_PATH")
    or _shutil.which("google-chrome")
    or _shutil.which("chromium")
    or _shutil.which("chromium-browser")
    or _shutil.which("chrome")
    or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)
PORT = int(os.getenv("CDP_PORT", "9333"))
QA_DIR = Path(os.getenv("QA_DIR") or (Path(__file__).parent / "qa"))
PROFILE = QA_DIR / "cdp-profile"
SHOTS = QA_DIR / "local"
SHOTS.mkdir(parents=True, exist_ok=True)
BASE = os.getenv("UI_BASE", "http://127.0.0.1:8000")


def http_json(path: str, method: str = "GET"):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


class CDP:
    def __init__(self, ws_url: str) -> None:
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.n = 0

    def send(self, method: str, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def eval(self, expr: str):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def shot(self, path: Path) -> None:
        data = self.send("Page.captureScreenshot", format="png")["data"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(data))

    def close(self) -> None:
        self.ws.close()


def main() -> int:
    if PROFILE.exists():
        shutil.rmtree(PROFILE, ignore_errors=True)
    proc = subprocess.Popen(
        [
            CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
            f"--user-data-dir={PROFILE}", "--window-size=1440,900",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            try:
                http_json("/json/version")
                break
            except Exception:
                time.sleep(0.5)
        target = http_json(f"/json/new?{BASE}/login", method="PUT")
        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")

        deadline = time.time() + 30
        while time.time() < deadline:
            if cdp.eval("document.readyState") == "complete" and cdp.eval("location.host"):
                break
            time.sleep(0.5)

        cdp.eval(
            """
(() => {
  const hash = (s) => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0; return 'h' + h.toString(36); };
  const acc = { id: 'u_demo01', nickname: '演示同学', passHash: hash('1234'), createdAt: Date.now() };
  localStorage.setItem('knock.accounts', JSON.stringify([acc]));
  localStorage.setItem('knock.currentAccount', acc.id);
  localStorage.setItem('knock.tourDone', '1');
  localStorage.setItem('knock.nick', '演示同学');
  return 'seeded';
})()
"""
        )
        cdp.send("Page.navigate", url=f"{BASE}/#/training/W-01")
        time.sleep(6)
        cdp.shot(SHOTS / "training_ui_1.png")

        filled = cdp.eval(
            """
(() => {
  const ta = document.querySelector('input[aria-label="输入你的回应"]');
  if (!ta) return 'no-input:' + location.pathname + '|' + document.body.innerText.slice(0, 120);
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(ta, '王阿姨您好，我是社区的小陈。今天想陪您聊聊最近的情况，您方便吗？');
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  return 'filled';
})()
"""
        )
        time.sleep(1)
        clicked = cdp.eval(
            """
(() => {
  const btn = document.querySelector('button.send');
  if (!btn) return 'no-send';
  if (btn.disabled) return 'send-disabled';
  btn.click();
  return 'clicked';
})()
"""
        )
        time.sleep(5)
        cdp.shot(SHOTS / "training_ui_2.png")
        snippet = cdp.eval("document.body.innerText.slice(0, 700)")
        print("filled:", filled, "| clicked:", clicked)
        print("--- page text ---")
        print(snippet)
        cdp.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ══════════════════════════════════════════════════════════════
# 公共启动器：统一 Chrome 启动与 CDP 连接
# ──────────────────────────────────────────────────────────────
# 为什么要收敛：8 个审查脚本原先各自复制了一份 Popen + 等待 + 连接逻辑，
# CI 上出现过 Chrome 已响应 /json/version 但 /json/new 尚未就绪、
# 导致 CDP websocket 连接被拒（ConnectionRefusedError）的竞态。
# 统一后可以集中加重试与容器友好参数，不必改 8 个文件。
# ══════════════════════════════════════════════════════════════

#: 容器/CI 环境必需：沙箱在部分 runner 上无法初始化，/dev/shm 过小会导致崩溃
CHROME_ARGS = [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-background-networking",
]


def launch_chrome(window_size: str = "1440,1200", profile: Path | None = None):
    """启动 Chrome 并返回 Popen。调用方负责 terminate。"""
    import subprocess

    prof = profile or PROFILE
    if prof.exists():
        shutil.rmtree(prof, ignore_errors=True)
    prof.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [CHROME, *CHROME_ARGS,
         f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
         f"--user-data-dir={prof}", f"--window-size={window_size}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def wait_cdp_ready(timeout: float = 45.0) -> None:
    """等待 CDP 端点可用。仅 /json/version 通不代表能建新 tab。"""
    end = time.time() + timeout
    last: Exception | None = None
    while time.time() < end:
        try:
            http_json("/json/version")
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.5)
    raise RuntimeError(f"CDP 端点 {timeout}s 内未就绪: {last}")


def open_page(base: str | None = None, window_size: str = "1440,1200",
              retries: int = 4) -> "CDP":
    """打开一个新页面并返回已连接的 CDP。

    对「建 tab 成功但 ws 连不上」的竞态做重试——这正是 CI 上踩到的失败模式。
    """
    url = base or BASE
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        wait_cdp_ready()
        try:
            target = http_json(f"/json/new?{url}/", method="PUT")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5)
            continue
        try:
            cdp = CDP(target["webSocketDebuggerUrl"])
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5)
            continue
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        time.sleep(2.5)
        return cdp
    raise RuntimeError(f"打开页面失败（重试 {retries} 次）: {last}")
