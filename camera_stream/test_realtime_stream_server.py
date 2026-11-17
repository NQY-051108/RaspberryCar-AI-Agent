#!/usr/bin/env python3
"""Small offline test for the runtime image-saving toggle."""
import unittest

import realtime_stream_server as server


class SaveToggleTests(unittest.TestCase):
    def setUp(self):
        server.SAVE_ENABLED = True
        server.SAVE_STATE_CHANGED = False

    def test_signal_toggles_save_state(self):
        server.toggle_save_handler(None, None)
        self.assertFalse(server.SAVE_ENABLED)
        self.assertTrue(server.SAVE_STATE_CHANGED)

        server.SAVE_STATE_CHANGED = False
        server.toggle_save_handler(None, None)
        self.assertTrue(server.SAVE_ENABLED)
        self.assertTrue(server.SAVE_STATE_CHANGED)


if __name__ == "__main__":
    unittest.main()
