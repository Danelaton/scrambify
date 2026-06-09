from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from scrambify.config import AppConfig


class AppConfigTests(unittest.TestCase):
    def test_default_reads_environment_overrides(self) -> None:
        env = {
            "SCRAMBIFY_RENDEZVOUS_URL": "http://127.0.0.1:4999/v1",
            "SCRAMBIFY_TRANSIT_URL": "tcp://127.0.0.1:4001",
            "SCRAMBIFY_CODE_WORD_COUNT": "3",
        }

        with patch.dict(os.environ, env, clear=False):
            config = AppConfig.default()

        self.assertEqual(config.relay.rendezvous_url, env["SCRAMBIFY_RENDEZVOUS_URL"])
        self.assertEqual(config.relay.transit_url, env["SCRAMBIFY_TRANSIT_URL"])
        self.assertEqual(config.code_word_count, 3)