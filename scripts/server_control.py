"""Private localhost control channel for the PPTetrics data server.

The OBS WebSocket remains dedicated to the existing state JSON stream.
"""
import json
import secrets
import socket
from websockets.sync.client import connect as websocket_connect


PROTOCOL_VERSION = 1
SERVICE_NAME = "PPTetrics"


def request(host, port, message, timeout=1.0):
    """Send one JSON-line control request and return its JSON-line response."""
    wire = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(wire)
        chunks = bytearray()
        while b"\n" not in chunks:
            part = sock.recv(4096)
            if not part:
                raise ConnectionError("control server closed without a response")
            chunks.extend(part)
            if len(chunks) > 16384:
                raise ValueError("control response is too large")
    return json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))


def identify(host, port, timeout=1.0):
    response = request(host, port, {"command": "identify", "protocol": PROTOCOL_VERSION}, timeout)
    if (response.get("service") != SERVICE_NAME
            or response.get("protocol") != PROTOCOL_VERSION
            or not isinstance(response.get("instance_id"), str)):
        raise ValueError("control endpoint is not a compatible PPTetrics server")
    return response


def identify_legacy(host, port, timeout=1.0):
    """Recognize an older PPTetrics server by its existing state protocol.

    This is read-only compatibility: legacy instances have no authenticated
    control endpoint and are never considered owned or eligible for shutdown.
    """
    with websocket_connect(f"ws://{host}:{port}", open_timeout=timeout,
                           close_timeout=timeout, proxy=None) as ws:
        state = json.loads(ws.recv(timeout=timeout))
    if not (isinstance(state, dict) and isinstance(state.get("capture"), dict)
            and isinstance(state.get("display"), dict)
            and isinstance(state.get("page_rev"), str)):
        raise ValueError("WebSocket endpoint does not speak the PPTetrics state protocol")
    return {"service": SERVICE_NAME, "protocol": 0, "instance_id": "legacy-unmanaged", "pid": None}


def request_shutdown(host, port, instance_id, token, timeout=1.0):
    response = request(host, port, {
        "command": "shutdown", "protocol": PROTOCOL_VERSION,
        "instance_id": instance_id, "token": token,
    }, timeout)
    return response.get("accepted") is True and response.get("instance_id") == instance_id


def handle_control_message(message, instance_id, token, pid):
    """Build a control response and indicate whether authenticated shutdown is requested."""
    command = message.get("command")
    valid_protocol = message.get("protocol") == PROTOCOL_VERSION
    response = {"service": SERVICE_NAME, "protocol": PROTOCOL_VERSION,
                "instance_id": instance_id, "pid": pid}
    stop_requested = False
    if command == "shutdown":
        accepted = (valid_protocol and message.get("instance_id") == instance_id
                    and secrets.compare_digest(str(message.get("token", "")), token))
        response["accepted"] = accepted
        stop_requested = accepted
    elif command != "identify" or not valid_protocol:
        response = {"error": "unsupported request", "protocol": PROTOCOL_VERSION}
    return response, stop_requested


def server_pid_is_ours(server_pid, child_pid):
    """The server reports its own pid. Run from a virtual environment
    (.venv/Scripts/pythonw.exe, as the desktop shortcut does), the started
    process is a small launcher that runs the real interpreter as its child,
    so the server's pid is that child's: compare against both (the check
    refused every start there: "control port answered for a different server")."""
    if server_pid == child_pid:
        return True
    import psutil

    try:
        return server_pid in {c.pid for c in psutil.Process(child_pid).children(recursive=True)}
    except psutil.Error:
        return False
