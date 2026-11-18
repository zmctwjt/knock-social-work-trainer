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
