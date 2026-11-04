import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from server_control import handle_control_message, identify, identify_legacy, request_shutdown


class ServerControlTests(unittest.TestCase):
    def test_identify_rejects_unrelated_service(self):
        with patch("server_control.request", return_value={"service": "other"}):
            with self.assertRaises(ValueError):
                identify("127.0.0.1", 8766)

    def test_legacy_identification_requires_pptetrics_state_shape(self):
        class FakeWebSocket:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def recv(self, timeout):
                return '{"capture":{},"display":{},"page_rev":"rev"}'

        with patch("server_control.websocket_connect", return_value=FakeWebSocket()):
            identity = identify_legacy("127.0.0.1", 8765)
        self.assertEqual(identity["protocol"], 0)
        self.assertEqual(identity["instance_id"], "legacy-unmanaged")
        self.assertIsNone(identity["pid"])

        class OtherWebSocket(FakeWebSocket):
            def recv(self, timeout):
                return '{"ok":true}'

        with patch("server_control.websocket_connect", return_value=OtherWebSocket()):
            with self.assertRaises(ValueError):
                identify_legacy("127.0.0.1", 8765)

    def test_shutdown_needs_matching_protocol_instance_and_token(self):
        base = {"command": "shutdown", "protocol": 1,
                "instance_id": "owned-instance", "token": "secret"}
        response, stop = handle_control_message(base, "owned-instance", "secret", 123)
        self.assertTrue(response["accepted"])
        self.assertTrue(stop)

        for changes in ({"token": "wrong"}, {"instance_id": "other"}, {"protocol": 2}):
            message = {**base, **changes}
            response, stop = handle_control_message(message, "owned-instance", "secret", 123)
            self.assertFalse(response["accepted"])
            self.assertFalse(stop)

    def test_shutdown_client_requires_server_ack_for_same_instance(self):
        with patch("server_control.request", return_value={"accepted": True, "instance_id": "run-1"}) as send:
            self.assertTrue(request_shutdown("127.0.0.1", 8766, "run-1", "token"))
        sent = send.call_args.args[2]
        self.assertEqual(sent["command"], "shutdown")
        self.assertEqual(sent["token"], "token")


if __name__ == "__main__":
    unittest.main()


def test_a_venv_started_server_counts_as_ours():
    """From .venv the started process is a launcher whose child is the real
    server: its pid is the child's (the start was refused before)."""
    import subprocess
    import sys
    import time
    from server_control import server_pid_is_ours
    outer = subprocess.Popen([sys.executable, "-c",
                              "import subprocess, sys; subprocess.run([sys.executable, '-c', 'import time; time.sleep(5)'])"])
    try:
        import psutil
        inner = None
        for _ in range(50):
            kids = psutil.Process(outer.pid).children(recursive=True)
            if kids:
                inner = kids[-1].pid
                break
            time.sleep(0.1)
        assert inner is not None
        assert server_pid_is_ours(inner, outer.pid)
        assert server_pid_is_ours(outer.pid, outer.pid)
        assert not server_pid_is_ours(4, outer.pid)
    finally:
        for p in psutil.Process(outer.pid).children(recursive=True):
            p.kill()
        outer.kill()
