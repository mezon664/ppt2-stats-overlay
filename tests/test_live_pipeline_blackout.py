import unittest
from unittest.mock import Mock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from live_pipeline import MatchPipeline


class BlackoutResetTests(unittest.TestCase):
    @staticmethod
    def pipeline(frozen):
        pipeline = MatchPipeline.__new__(MatchPipeline)
        pipeline._frozen = frozen
        pipeline._startup_wait = False
        pipeline._fallback_saw_empty_since_freeze = False
        pipeline._blackout_handled = False
        pipeline.start_t = 42.0
        pipeline._play_started_t = 42.0
        pipeline.frame_count = 300
        pipeline.match_reset_count = 0
        pipeline._recreate_pipelines = Mock()
        return pipeline

    def test_concluded_match_data_and_clock_survive_black_transition(self):
        pipeline = self.pipeline(frozen=True)
        pipeline._blackout_reset()
        pipeline._recreate_pipelines.assert_not_called()
        self.assertEqual(pipeline.start_t, 42.0)
        self.assertTrue(pipeline._blackout_handled)
        self.assertEqual(pipeline.match_reset_count, 1)

    def test_in_progress_match_is_cleared_on_black_transition(self):
        pipeline = self.pipeline(frozen=False)
        pipeline._blackout_reset()
        pipeline._recreate_pipelines.assert_called_once_with()
        self.assertIsNone(pipeline.start_t)
        self.assertTrue(pipeline._frozen)
        self.assertTrue(pipeline._blackout_handled)


if __name__ == "__main__":
    unittest.main()
