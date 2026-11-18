"""一键启动本机演示环境（MySQL 3307 + FastAPI 8000 + Vite 5173）。

用法：
    work\\pyenv\\Scripts\\python.exe work\\start_local.py

幂等：已在监听的组件会跳过，不会重复启动。
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / "work" / "pyenv" / "Scripts" / "python.exe"
BACKEND = ROOT / "deliverables" / "backend"
FRONTEND = ROOT / "src_extract" / "01_作品及成果文件"
MYSQLD = Path(r"C:\Program Files\AppServ\MySQL\bin\mysqld.exe")
MY_INI = Path(r"F:\knock-mysql\my.ini")
LOG_DIR = ROOT / "work" / "logs"

DETACHED = 0x00000008 | 0x00000200


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def wait_port(port: int, seconds: int) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if port_open(port):
            return True
        time.sleep(0.5)
    return False


def spawn(args, cwd: Path, log_name: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_DIR / log_name, "ab", buffering=0)  # noqa: SIM115 - 交给子进程持有
    return subprocess.Popen(args, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT,
                            creationflags=DETACHED, close_fds=True)


def main() -> int:
    steps: list[str] = []

    if port_open(3307):
        steps.append("MySQL  已运行 127.0.0.1:3307")
    else:
        if not MYSQLD.exists() or not MY_INI.exists():
            print("找不到 mysqld 或 my.ini，无法启动数据库")
            return 1
        spawn([str(MYSQLD), f"--defaults-file={MY_INI.as_posix()}"], ROOT, "mysql.out.log")
        ok = wait_port(3307, 90)
        steps.append(("MySQL  已启动 127.0.0.1:3307" if ok else "MySQL  启动失败，看 work/logs/mysql.out.log"))

    if port_open(8000):
        steps.append("后端   已运行 http://127.0.0.1:8000")
    else:
        spawn([str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
              BACKEND, "backend.out.log")
        ok = wait_port(8000, 60)
        steps.append("后端   已启动 http://127.0.0.1:8000" if ok else "后端   启动失败，看 work/logs/backend.out.log")

    if port_open(5173):
        steps.append("前端   已运行 http://localhost:5173/")
    else:
        env_note = "PORT=8000"
        spawn(["cmd.exe", "/c", f"set {env_note}&& npm run dev"], FRONTEND, "vite.out.log")
        ok = wait_port(5173, 60)
        steps.append("前端   已启动 http://localhost:5173/" if ok else "前端   启动失败，看 work/logs/vite.out.log")

    ready = ""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/readyz", timeout=3) as r:
            ready = r.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        ready = f"未就绪：{exc}"

    print("\n".join(f"  {s}" for s in steps))
    print("  /readyz:", ready)
    print("\n浏览器打开  http://localhost:5173/  注册任意账号即可训练")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
