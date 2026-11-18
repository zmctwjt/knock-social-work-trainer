"""以分离进程方式启动后端（不依赖调用方 shell 存活）。

用法：python work/launch_backend.py [port]
日志：work/logs/backend.out.log
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "deliverables" / "backend"
PYTHON = ROOT / "work" / "pyenv" / "Scripts" / "python.exe"
LOG = ROOT / "work" / "logs" / "backend.out.log"

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG, "ab", buffering=0)
    proc = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
        cwd=str(BACKEND),
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    print(f"backend pid={proc.pid} port={port} log={LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
