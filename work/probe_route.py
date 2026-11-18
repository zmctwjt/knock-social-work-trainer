"""诊断：/cases 与 /training/W-01 两个路由实际渲染了什么。"""
from __future__ import annotations

import shutil
import subprocess
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ui_smoke import BASE, CDP, CHROME, PORT, PROFILE, SHOTS, http_json  # noqa: E402

SEED = """
(() => {
  const hash = (s) => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0; return 'h' + h.toString(36); };
  const acc = { id: 'u_demo01', nickname: '演示同学', passHash: hash('1234'), createdAt: Date.now() };
  localStorage.setItem('knock.accounts', JSON.stringify([acc]));
  localStorage.setItem('knock.currentAccount', acc.id);
  localStorage.setItem('knock.tourDone', '1');
  localStorage.setItem('knock.nick', '演示同学');
  return 'ok';
})()
"""

DUMP = """
(() => {
  const h = [...document.querySelectorAll('h1,h2')].map(x => x.innerText.trim()).slice(0,3).join(' / ');
  const inp = document.querySelectorAll('input').length;
  return location.pathname + ' | h=' + h + ' | inputs=' + inp + ' | len=' + document.body.innerText.length;
})()
"""


def main() -> int:
    if PROFILE.exists():
        shutil.rmtree(PROFILE, ignore_errors=True)
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
         f"--user-data-dir={PROFILE}", "--window-size=1440,900", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            try:
                http_json("/json/version")
                break
            except Exception:
                time.sleep(0.5)
        target = http_json("/json/new?" + BASE + "/login", method="PUT")
        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        time.sleep(3)
        print("seed:", cdp.eval(SEED))
        for path in ("/cases", "/training/W-01"):
            cdp.send("Page.navigate", url=BASE + path)
            time.sleep(5)
            print(path, "->", cdp.eval(DUMP))
            cdp.shot(SHOTS / ("probe_" + path.strip("/").replace("/", "_") + ".png"))
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
