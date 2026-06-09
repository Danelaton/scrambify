from __future__ import annotations

import unittest

from scrambify.cli import build_parser


class CliParserTests(unittest.TestCase):
    def test_send_parser_accepts_text_payload(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["send", "--text", "hello", "--timeout", "5"])

        self.assertEqual(args.command, "send")
        self.assertEqual(args.text, "hello")
        self.assertIsNone(args.file)
        self.assertEqual(args.timeout, 5.0)

    def test_send_parser_requires_a_payload(self) -> None:
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["send"])

    def test_receive_parser_accepts_output_path(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["receive", "7-sunrise-meadow", "--output", "downloads"])

        self.assertEqual(args.command, "receive")
        self.assertEqual(args.code, "7-sunrise-meadow")
        self.assertEqual(args.output, "downloads")