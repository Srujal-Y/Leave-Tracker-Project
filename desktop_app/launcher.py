from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 3000
BACKEND_HEALTH_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health/"
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}/login"


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def find_project_root() -> Path:
    candidates = [
        Path.cwd(),
        Path(sys.executable).resolve().parent,
        Path(sys.executable).resolve().parent.parent,
    ]
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(Path(meipass))

    for candidate in _unique_paths(candidates):
        for path in [candidate, *candidate.parents]:
            if not (path / "manage.py").exists():
                continue
            if not (path / "frontend" / "package.json").exists():
                continue
            return path

    raise RuntimeError(
        "Could not locate project root (manage.py + frontend/package.json). "
        "Place this EXE inside the project folder or dist subfolder."
    )


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def wait_for_url(url: str, timeout_seconds: int = 90) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return True
        except URLError:
            pass
        except Exception:
            pass
        time.sleep(1)
    return False


def wait_for_service(url: str, timeout_seconds: int = 60, proc: subprocess.Popen | None = None) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return True
        except URLError:
            pass
        except Exception:
            pass
        time.sleep(1)
    return False


def run_setup_command(cmd: list[str], cwd: Path, env: dict[str, str], log_handle, label: str) -> int:
    print(f"Running setup: {label}")
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.returncode


def main() -> int:
    backend_proc: subprocess.Popen | None = None
    frontend_proc: subprocess.Popen | None = None
    backend_log = None
    frontend_log = None

    try:
        root = find_project_root()
        logs_dir = root / "desktop_app" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        backend_log = open(logs_dir / "backend.log", "a", encoding="utf-8")
        frontend_log = open(logs_dir / "frontend.log", "a", encoding="utf-8")

        print(f"Project root: {root}")
        print(f"Logs: {logs_dir}")

        py_exe = root / ".venv" / "Scripts" / "python.exe"
        if not py_exe.exists():
            print("Missing .venv\\Scripts\\python.exe. Create venv and install dependencies first.")
            return 1

        npm_cmd = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm_cmd:
            print("npm is not installed or not in PATH.")
            return 1

        backend_env = os.environ.copy()
        backend_env["USE_DATABASE_URL"] = "0"
        backend_env["ALLOWED_HOSTS"] = "127.0.0.1,localhost"
        backend_env["DEBUG"] = "1"

        if not is_port_open(BACKEND_HOST, BACKEND_PORT):
            migrate_code = run_setup_command(
                [str(py_exe), "manage.py", "migrate", "--noinput"],
                cwd=root,
                env=backend_env,
                log_handle=backend_log,
                label="database migrations",
            )
            if migrate_code != 0:
                print("Migration step failed. Check backend.log")
                return 1

            bootstrap_code = run_setup_command(
                [str(py_exe), "manage.py", "bootstrap_leave_data"],
                cwd=root,
                env=backend_env,
                log_handle=backend_log,
                label="bootstrap leave data",
            )
            if bootstrap_code != 0:
                print("Bootstrap step failed. Check backend.log")
                return 1

            print("Starting backend...")
            backend_proc = subprocess.Popen(
                [str(py_exe), "manage.py", "runserver", f"{BACKEND_HOST}:{BACKEND_PORT}", "--noreload", "--insecure"],
                cwd=str(root),
                stdout=backend_log,
                stderr=subprocess.STDOUT,
                env=backend_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            print(f"Backend already running at {BACKEND_HOST}:{BACKEND_PORT}.")

        frontend_env = os.environ.copy()
        frontend_env["NEXT_PUBLIC_API_BASE_URL"] = f"http://{BACKEND_HOST}:{BACKEND_PORT}/api"

        lock_path = root / "frontend" / ".next" / "dev" / "lock"
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass

        if not is_port_open(FRONTEND_HOST, FRONTEND_PORT):
            print("Starting frontend...")
            frontend_proc = subprocess.Popen(
                [
                    npm_cmd,
                    "--prefix",
                    str(root / "frontend"),
                    "run",
                    "dev",
                    "--",
                    "--webpack",
                    "--hostname",
                    FRONTEND_HOST,
                    "--port",
                    str(FRONTEND_PORT),
                ],
                cwd=str(root),
                stdout=frontend_log,
                stderr=subprocess.STDOUT,
                env=frontend_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            print(f"Frontend already running at {FRONTEND_HOST}:{FRONTEND_PORT}.")

        print("Waiting for backend health endpoint...")
        backend_ok = wait_for_service(BACKEND_HEALTH_URL, timeout_seconds=45, proc=backend_proc)
        print("Waiting for frontend...")
        frontend_ok = wait_for_service(FRONTEND_URL, timeout_seconds=60, proc=frontend_proc)

        if backend_ok and frontend_ok:
            print(f"Opening {FRONTEND_URL}")
            webbrowser.open(FRONTEND_URL)
        else:
            print("Startup warning: one or more services did not become ready in time.")
            print(f"Check logs in: {logs_dir}")

    except KeyboardInterrupt:
        print("Stopping services...")
    except Exception as exc:
        print(f"Launcher error: {exc}")
        print("Press Enter to close.")
        try:
            input()
        except EOFError:
            pass
        return 1
    finally:
        if backend_log:
            backend_log.close()
        if frontend_log:
            frontend_log.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
