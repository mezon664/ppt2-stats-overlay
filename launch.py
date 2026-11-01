"""One-click start: runs the recognition server in the background and the
HUD (with its tray icon and settings window) in front. Quitting the HUD from
the tray also stops the server it started.

Double-click start.bat (no console window), or: python launch.py
Server output goes to logs/server.log.
"""

import atexit
import json
import os
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# pythonw.exeでも起動時のエラーを記録する
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

_launch_log = open(
    LOG_DIR / "launch.log",
    "a",
    encoding="utf-8",
    buffering=1
)

sys.stdout = _launch_log
sys.stderr = _launch_log

print("\n========== PPTetrics launch ==========")
print("Python:", sys.executable)
print("Arguments:", sys.argv)


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hud"))

from config_store import load_settings  # noqa: E402
import psutil  # noqa: E402
from server_control import identify, identify_legacy, request_shutdown  # noqa: E402


def server_already_running(host, port):
    """Return the identity of a compatible PPTetrics server, if one answers."""
    try:
        return identify(host, port + 1, timeout=0.5)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    try:
        return identify_legacy(host, port, timeout=0.5)
    except Exception:
        return None


def _acquire_start_lock(path, host, control_port, timeout=15):
    """Serialize launcher startup; never remove a lock owned by a live process."""
    deadline = time.monotonic() + timeout
    lock_id = uuid.uuid4().hex
    payload = {"pid": os.getpid(), "lock_id": lock_id, "created": time.time()}
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
                f.flush()
                os.fsync(f.fileno())
            return lock_id
        except FileExistsError:
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                owner_pid = int(existing["pid"])
                owner_alive = psutil.pid_exists(owner_pid)
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                owner_alive = True  # ambiguous lock: fail safe and wait, never delete it
                existing = {}
            if not owner_alive:
                # Only reclaim a well-formed lock whose recorded owner is gone.
                try:
                    current = json.loads(path.read_text(encoding="utf-8"))
                    if current.get("lock_id") == existing.get("lock_id"):
                        path.unlink()
                except (OSError, ValueError, json.JSONDecodeError):
                    pass
                continue
            server = server_already_running(host, control_port - 1)
            if server:
                return None
            if time.monotonic() >= deadline:
                raise TimeoutError("another PPTetrics launch is still starting (or its lock is ambiguous)")
            time.sleep(0.1)


def _release_start_lock(path, lock_id):
    if not lock_id:
        return
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
        if current.get("lock_id") == lock_id:
            path.unlink()
    except (OSError, ValueError, json.JSONDecodeError):
        print("Could not safely release startup lock")


def _owned_child(handle):
    """Verify the Popen child is still the exact process this launch created."""
    proc = handle["proc"]
    if proc.poll() is not None:
        return False, "child already exited"
    try:
        child = psutil.Process(proc.pid)
        exe = os.path.normcase(os.path.realpath(child.exe()))
        expected_exe = os.path.normcase(os.path.realpath(sys.executable))
        cmdline = [os.path.normcase(os.path.realpath(x)) if os.path.isabs(x) else x
                   for x in child.cmdline()]
        expected_script = os.path.normcase(os.path.realpath(ROOT / "scripts" / "data_server.py"))
        if abs(child.create_time() - handle["create_time"]) > 1.0:
            return False, "process start time changed"
        if exe != expected_exe or expected_script not in cmdline:
            return False, "executable or server script does not match"
        if "--instance-id" not in cmdline or handle["instance_id"] not in cmdline:
            return False, "launch ID is missing from child command line"
        return True, "verified"
    except (psutil.Error, OSError, ValueError) as e:
        return False, f"process ownership could not be verified: {e}"


def start_server():
    settings = load_settings()
    host, port = settings["server"]["host"], settings["server"]["port"]
    if not isinstance(port, int) or not 1 <= port < 65535:
        raise ValueError(f"server port must be between 1 and 65534 for the control channel: {port!r}")
    control_host, control_port = "127.0.0.1", port + 1
    existing = server_already_running(host, port)
    if existing:
        print(f"Attached to identified PPTetrics server instance_id={existing['instance_id']} pid={existing.get('pid')}")
        return None
    lock_path = ROOT / "logs" / "server-start.lock"
    lock_id = _acquire_start_lock(lock_path, host, control_port)
    if lock_id is None:
        existing = server_already_running(host, port)
        if existing:
            print(f"Attached to concurrently started PPTetrics server instance_id={existing['instance_id']}")
            return None
        raise RuntimeError("startup lock is held but no identifiable PPTetrics server is ready")
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}   # the log has Japanese in it
    instance_id, token = uuid.uuid4().hex, uuid.uuid4().hex + uuid.uuid4().hex
    cmd = [sys.executable, str(ROOT / "scripts" / "data_server.py"), "--source", "live",
           "--control-host", control_host, "--control-port", str(control_port),
           "--instance-id", instance_id, "--control-token", token]
    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT / "scripts"), stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, creationflags=flags, env=env, close_fds=True)
        try:
            create_time = psutil.Process(proc.pid).create_time()
        except (psutil.Error, OSError) as e:
            proc.wait(timeout=0.1) if proc.poll() is not None else None
            raise RuntimeError(f"could not record server process identity: {e}") from e
        handle = {"proc": proc, "create_time": create_time, "instance_id": instance_id,
                  "token": token, "host": control_host, "port": control_port,
                  "stopped": False}
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"data_server exited during startup (code {proc.returncode}); check logs/server.log")
            try:
                identity = identify(control_host, control_port, timeout=0.3)
                valid, reason = _owned_child(handle)
                if identity.get("instance_id") == instance_id and identity.get("pid") == proc.pid and valid:
                    print(f"Server ready instance_id={instance_id} pid={proc.pid}")
                    handle["atexit_callback"] = lambda: stop_server(handle)
                    atexit.register(handle["atexit_callback"])
                    return handle
                if identity.get("instance_id") != instance_id or identity.get("pid") != proc.pid:
                    raise RuntimeError("control port answered for a different server; refusing to attach")
                if not valid:
                    raise RuntimeError(f"server process identity check failed: {reason}")
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                time.sleep(0.1)
        raise TimeoutError("data_server did not complete its identity handshake within 15 seconds")
    except Exception:
        # A process started here may be stopped only after the same ownership checks.
        if "handle" in locals():
            stop_server(handle)
        elif "proc" in locals() and proc.poll() is None:
            # proc is the Popen handle returned for this exact child, so this
            # emergency cleanup does not reopen or target a process by PID.
            print(f"Startup failed; stopping this launch's unverified child pid={proc.pid} via its Popen handle")
            try:
                proc.terminate()
                proc.wait(timeout=3)
                print(f"Unverified child exit confirmed pid={proc.pid} code={proc.returncode}")
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                    print(f"Unverified child killed and exit confirmed pid={proc.pid} code={proc.returncode}")
                except (OSError, subprocess.TimeoutExpired) as e:
                    print(f"Could not confirm unverified child exit pid={proc.pid}: {e}")
            except OSError as e:
                print(f"Could not stop this launch's child pid={proc.pid}: {e}")
        raise
    finally:
        _release_start_lock(lock_path, lock_id)


def stop_server(handle):
    if handle["stopped"]:
        return
    handle["stopped"] = True
    proc = handle["proc"]
    print(f"Shutdown requested instance_id={handle['instance_id']} pid={proc.pid}")
    try:
        accepted = request_shutdown(handle["host"], handle["port"], handle["instance_id"], handle["token"])
        print(f"Control shutdown {'accepted' if accepted else 'rejected'} instance_id={handle['instance_id']}")
    except Exception as e:
        accepted = False
        print(f"Control shutdown failed instance_id={handle['instance_id']}: {e}")
    try:
        proc.wait(timeout=5)
        print(f"Server exit confirmed instance_id={handle['instance_id']} code={proc.returncode}")
        return
    except subprocess.TimeoutExpired:
        print(f"Server did not exit after control request (accepted={accepted}) instance_id={handle['instance_id']}")
    owned, reason = _owned_child(handle)
    if not owned:
        print(f"Refusing OS termination instance_id={handle['instance_id']}: {reason}")
        return
    try:
        proc.terminate()
        print(f"OS terminate sent instance_id={handle['instance_id']}")
        proc.wait(timeout=3)
        print(f"Server exit confirmed after terminate instance_id={handle['instance_id']} code={proc.returncode}")
        return
    except subprocess.TimeoutExpired:
        print(f"Server still running after terminate instance_id={handle['instance_id']}")
    except OSError as e:
        print(f"OS terminate failed instance_id={handle['instance_id']}: {e}")
        if proc.poll() is not None:
            print(f"Server exit confirmed after terminate error instance_id={handle['instance_id']} code={proc.returncode}")
            return
    owned, reason = _owned_child(handle)
    if not owned:
        print(f"Refusing force termination instance_id={handle['instance_id']}: {reason}")
        return
    try:
        proc.kill()
        print(f"OS kill sent instance_id={handle['instance_id']}")
        proc.wait(timeout=3)
        print(f"Server exit confirmed after kill instance_id={handle['instance_id']} code={proc.returncode}")
    except subprocess.TimeoutExpired:
        print(f"Server termination could not be confirmed instance_id={handle['instance_id']}")
    except OSError as e:
        print(f"Server kill failed instance_id={handle['instance_id']}: {e}")


def main():
    handle = start_server()
    try:
        import overlay  # hud/overlay.py
        overlay.main()  # runs until "終了 / Quit" in the tray menu
    finally:
        if handle:
            try:
                atexit.unregister(handle["atexit_callback"])
            except Exception:
                pass
            stop_server(handle)


if __name__ == "__main__":
    main()
