"""叩门 · 社工个案面谈 AI 陪练舱 —— 一键启动（Windows 本机演示版）

做四件事，全部幂等：
1. 起 MySQL（本机 AppServ 自带 8.0.17 二进制 + 项目私有数据目录，端口 3307）；
2. 迁移数据库（alembic upgrade head）+ 首次写入 12 个案例、19 张技巧卡；
3. 构建前端（dist 不存在或缺 index.html 时）；
4. 起 FastAPI 并同源托管前端（默认 http://127.0.0.1:8000 单端口）。

用法：
    work\\pyenv\\Scripts\\python.exe work\\run_all.py [--port 8000] [--dev] [--no-browser]

    start.bat            双击等价于 run_all.py
    --dev                前端改用 Vite 开发服务器（5173，热更新），接口仍走后端
    --no-browser         不自动打开浏览器
日志：work\\logs\\{mysql,backend,vite,build}.log
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / "work" / "pyenv" / "Scripts" / "python.exe"
BACKEND = ROOT / "deliverables" / "backend"
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
LOG_DIR = ROOT / "work" / "logs"
ENV_FILE = BACKEND / ".env"

MYSQLD = Path(r"C:\Program Files\AppServ\MySQL\bin\mysqld.exe")
MY_INI = Path(r"F:\knock-mysql\my.ini")
MYSQL_PORT = 3307

DETACHED = 0x00000008 | 0x00000200
STEPS: list[tuple[bool, str]] = []


def ok(msg: str) -> None:
    STEPS.append((True, msg))
    print(f"  [OK]   {msg}")


def warn(msg: str) -> None:
    STEPS.append((False, msg))
    print(f"  [WARN] {msg}")


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def wait_port(port: int, seconds: int, host: str = "127.0.0.1") -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if port_open(port, host):
            return True
        time.sleep(0.5)
    return False


def spawn(args: list[str], cwd: Path, log_name: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_DIR / log_name, "ab", buffering=0)  # noqa: SIM115 —— 由子进程持有
    return subprocess.Popen(
        args,
        cwd=str(cwd),
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=DETACHED,
        close_fds=True,
    )


def http_json(url: str, timeout: float = 3.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


# ── 1. MySQL ────────────────────────────────────────────────
def ensure_mysql() -> bool:
    if port_open(MYSQL_PORT):
        ok(f"MySQL 已在运行 127.0.0.1:{MYSQL_PORT}")
        return True
    if not MYSQLD.exists():
        warn(f"未找到 mysqld：{MYSQLD}")
        return False
    if not MY_INI.exists():
        warn(f"未找到数据库配置：{MY_INI}")
        return False
    spawn([str(MYSQLD), f"--defaults-file={MY_INI.as_posix()}"], ROOT, "mysql.out.log")
    if wait_port(MYSQL_PORT, 90):
        ok(f"MySQL 已启动 127.0.0.1:{MYSQL_PORT}")
        return True
    warn("MySQL 启动超时，见 work/logs/mysql.out.log")
    return False


# ── 2. 数据库迁移与种子 ──────────────────────────────────────
def ensure_schema() -> bool:
    if not ENV_FILE.exists():
        warn("缺少 deliverables/backend/.env，跳过迁移（首次请先复制 env.example）")
        return False
    url = ""
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip()
    if not url:
        warn(".env 中未配置 DATABASE_URL")
        return False
    env = dict(os.environ, DATABASE_URL=url, PYTHONIOENCODING="utf-8")
    alembic = PY.parent / "alembic.exe"
    # alembic 没有 __main__，必须用控制台脚本；找不到时退回 python -c 调用
    cmd = ([str(alembic), "upgrade", "head"] if alembic.exists()
           else [str(PY), "-c", "from alembic.config import main; main(argv=['upgrade','head'])"])
    res = subprocess.run(cmd, cwd=str(BACKEND), env=env, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=180)
    if res.returncode != 0:
        warn(f"数据库迁移失败：{(res.stderr or res.stdout)[-300:]}")
        return False
    ok("数据库结构已是最新（alembic upgrade head）")

    seed = subprocess.run([str(PY), "scripts/seed.py"], cwd=str(BACKEND), env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180)
    if seed.returncode == 0:
        # 种子脚本幂等：已存在则跳过，输出的 0 表示"无需新增"而非"没有数据"
        detail = seed.stdout.strip().replace("seed ok:", "").strip()
        ok(f"案例与知识卡已就绪（{detail} 为本次新增数，0 表示库中已有）")
    else:
        warn(f"种子数据写入失败：{(seed.stderr or seed.stdout)[-200:]}")
    return True


# ── 3. 前端构建 ─────────────────────────────────────────────
def ensure_frontend() -> bool:
    if (DIST / "index.html").exists():
        ok("前端产物已存在（dist/index.html）")
        return True
    if not (FRONTEND / "node_modules").exists():
        warn("前端依赖未安装，请在 frontend 目录下执行 npm ci")
        return False
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "build.log"
    with open(log_path, "ab") as log:
        res = subprocess.run(
            ["node", "node_modules/vite/bin/vite.js", "build"],
            cwd=str(FRONTEND), stdout=log, stderr=subprocess.STDOUT, timeout=600,
        )
    if res.returncode == 0 and (DIST / "index.html").exists():
        ok("前端已构建（work/logs/build.log）")
        return True
    warn("前端构建失败，见 work/logs/build.log")
    return False


# ── 4. 后端 ─────────────────────────────────────────────────
def ensure_backend(port: int) -> bool:
    if port_open(port):
        ok(f"后端已在运行 http://127.0.0.1:{port}")
        return True
    spawn([str(PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
          BACKEND, "backend.out.log")
    if not wait_port(port, 90):
        warn("后端启动超时，见 work/logs/backend.out.log")
        return False
    ok(f"后端已启动 http://127.0.0.1:{port}")
    return True


def ensure_vite(port: int = 5173) -> bool:
    if port_open(port):
        ok(f"前端开发服务器已在运行 http://localhost:{port}")
        return True
    spawn(["cmd.exe", "/c", f"set PORT={8000}&& npm run dev"], FRONTEND, "vite.out.log")
    if wait_port(port, 90):
        ok(f"前端开发服务器已启动 http://localhost:{port}")
        return True
    warn("Vite 启动超时，见 work/logs/vite.out.log")
    return False


def report(port: int, dev: bool) -> None:
    url = f"http://localhost:{port}"
    try:
        ready = http_json(f"http://127.0.0.1:{port}/readyz")["data"]
        db = next((c["detail"] for c in ready["checks"] if c["name"] == "database"), "?")
        cache = next((c["detail"] for c in ready["checks"] if c["name"] == "cache"), "?")
        ai = next((c["detail"] for c in ready["checks"] if c["name"] == "ai"), "?")
        line = f"数据库 {db} · 缓存 {cache} · AI {ai}"
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
        line = f"就绪探针读取失败：{exc}"
    print()
    print("  " + "─" * 56)
    print(f"   访问地址   {url}")
    if dev:
        print("   开发模式   前端 http://localhost:5173（热更新）")
    print(f"   健康检查   {url}/healthz    就绪 {url}/readyz")
    print(f"   接口文档   {url}/docs")
    print(f"   运行状态   {line}")
    print("  " + "─" * 56)
    print("   演示账号   student01 / Student@12345   （学生）")
    print("              teacher01 / Teacher@12345   （教师）")
    print("              admin01   / Admin@12345     （管理员）")
    print("   账号说明   不开放自助注册，由管理员在「管理后台 → 账号管理」创建。")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="叩门 AI 陪练舱 一键启动")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--dev", action="store_true", help="前端用 Vite 开发服务器（热更新）")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    print()
    print("=" * 60)
    print("  叩门 · 社工个案面谈 AI 陪练舱 —— 启动中")
    print("=" * 60)

    if not PY.exists():
        print(f"  [错误] 未找到运行时：{PY}")
        return 2

    ensure_mysql()
    ensure_schema()
    front_ok = ensure_frontend()
    back_ok = ensure_backend(args.port)

    if args.dev:
        ensure_vite()

    if not back_ok:
        print()
        print("  后端未就绪，以下服务无法确认，先看日志再重试。")
        return 1

    url_port = args.port
    report(url_port, args.dev)
    if not front_ok and not args.dev:
        warn("前端产物缺失，单端口模式只能访问接口文档（/docs）")

    if not args.no_browser:
        target = "http://localhost:5173" if args.dev else f"http://localhost:{url_port}"
        try:
            webbrowser.open(target)
        except Exception:  # noqa: BLE001 —— 打不开浏览器不算失败
            pass

    failed = [m for good, m in STEPS if not good]
    if failed:
        print(f"  提示：{len(failed)} 项需要关注（见上方 WARN 与 work/logs/）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
