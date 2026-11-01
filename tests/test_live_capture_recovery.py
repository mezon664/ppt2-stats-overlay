import threading
import unittest
from pathlib import Path
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import data_server


class LiveCaptureRecoveryTests(unittest.TestCase):
    def test_capture_exception_marks_failure_and_retries_without_killing_server_loop(self):
        stopped = threading.Event()
        created = []

        class Capture:
            def __init__(self, fails):
                self.fails = fails
                self.closed = False

            def grab(self):
                if self.fails:
                    raise RuntimeError("temporary capture failure")
                return object(), True, None, type("Profile", (), {
                    "client_w": 1232, "client_h": 692, "scale_x": 1.0})()

            def close(self):
                self.closed = True

        def factory():
            capture = Capture(fails=not created)
            created.append(capture)
            return capture

        pipeline = Mock()
        pipeline.process_frame.side_effect = lambda *_: stopped.set()
        original_pipeline, original_status = data_server.PIPELINE, data_server.CAPTURE_STATUS
        try:
            data_server.PIPELINE = pipeline
            data_server.CAPTURE_STATUS = {"ok": True, "message": "previous state"}
            with patch.object(data_server.log, "exception"):
                data_server.capture_loop_live(fps_target=1000, stop_event=stopped,
                                             capture_factory=factory)
            self.assertEqual(len(created), 2)
            self.assertTrue(created[0].closed)
            self.assertEqual(data_server.CAPTURE_STATUS["ok"], True)
            self.assertEqual(data_server.CAPTURE_STATUS["message"], "capturing")
            pipeline.process_frame.assert_called_once()
        finally:
            data_server.PIPELINE, data_server.CAPTURE_STATUS = original_pipeline, original_status


if __name__ == "__main__":
    unittest.main()
