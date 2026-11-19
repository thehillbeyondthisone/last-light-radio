"""The comparison routes must dispatch read-only helpers, preserving old media routes."""

import unittest
from unittest.mock import patch

from last_light_radio.server import make_server
from last_light_radio.studio import StudioError


class TakeReviewRouteTests(unittest.TestCase):
    def setUp(self):
        self.studio = object()
        self.server = make_server(self.studio, 0)
        self.addCleanup(self.server.server_close)
        self.handler = object.__new__(self.server.RequestHandlerClass)

    def dispatch(self, parts):
        with patch.object(self.handler, "guard_host"), patch.object(self.handler, "path_parts", return_value=parts), \
                patch.object(self.handler, "send_json") as send_json, patch.object(self.handler, "send_bytes") as send_bytes:
            self.handler.dispatch()
        return send_json, send_bytes

    def test_numeric_frame_uses_validated_decoder_and_preserves_bytes(self):
        with patch("last_light_radio.take_review.decoded_frame", return_value=b"exact-png") as decode:
            sent_json, sent_bytes = self.dispatch(["api", "candidates", "a", "frames", "17"])
        decode.assert_called_once_with(self.studio, "a", 17)
        sent_bytes.assert_called_once_with(b"exact-png", "image/png")
        sent_json.assert_not_called()

    def test_comparison_uses_read_only_diagnostics(self):
        result = {"advisory_only": True, "approval_changed": False}
        with patch("last_light_radio.take_review.compare_takes", return_value=result) as compare:
            sent_json, sent_bytes = self.dispatch(["api", "candidates", "a", "compare", "b"])
        compare.assert_called_once_with(self.studio, "a", "b")
        sent_json.assert_called_once_with(result)
        sent_bytes.assert_not_called()

    def test_invalid_or_changed_candidate_is_reported_visibly(self):
        with patch("last_light_radio.take_review.decoded_frame", side_effect=StudioError("Candidate changed", 409)):
            sent_json, sent_bytes = self.dispatch(["api", "candidates", "a", "frames", "999"])
        sent_json.assert_called_once_with({"error": {"message": "Candidate changed"}}, 409)
        sent_bytes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
