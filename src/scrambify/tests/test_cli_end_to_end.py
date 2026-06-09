from __future__ import annotations

from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from scrambify.protocol.relay import RelayMailboxRepository, RelayRequestHandler


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class CliEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        RelayRequestHandler.repository = RelayMailboxRepository()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RelayRequestHandler)
        self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)

    def test_file_transfer_via_cli_processes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.txt"
            destination_dir = temp_path / "downloads"
            destination_dir.mkdir()
            destination_path = destination_dir / source_path.name
            payload = "scrambify file payload\n" * 12
            source_path.write_text(payload, encoding="utf-8", newline="\n")

            sender = self._spawn(
                "send",
                "--file",
                str(source_path),
                "--timeout",
                "10",
                "--poll-interval",
                "0.05",
            )
            try:
                code_line = sender.stdout.readline().strip()
                self.assertIn("Scrambify code is:", code_line)
                code = code_line.rsplit(": ", 1)[1]

                receiver = self._spawn(
                    "receive",
                    code,
                    "--output-dir",
                    str(destination_dir),
                    "--timeout",
                    "10",
                    "--poll-interval",
                    "0.05",
                )
                try:
                    receiver_stdout, receiver_stderr = receiver.communicate(timeout=15)
                finally:
                    if receiver.poll() is None:
                        receiver.kill()
                sender_stdout_rest, sender_stderr = sender.communicate(timeout=15)
            finally:
                if sender.poll() is None:
                    sender.kill()

            sender_stdout = "\n".join(part for part in [code_line, sender_stdout_rest.strip()] if part)
            self.assertEqual(sender.returncode, 0, msg=sender_stderr)
            self.assertEqual(receiver.returncode, 0, msg=receiver_stderr)
            self.assertEqual(destination_path.read_text(encoding="utf-8"), payload)
            self.assertIn("sent file source.txt", sender_stdout)
            self.assertIn("received file source.txt", receiver_stdout)

    def test_file_transfer_saves_to_receiver_working_directory_by_default(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.txt"
            receiver_dir = temp_path / "receiver"
            receiver_dir.mkdir()
            payload = "scrambify file payload\n" * 12
            source_path.write_text(payload, encoding="utf-8", newline="\n")

            sender = self._spawn(
                "send",
                "--file",
                str(source_path),
                "--timeout",
                "10",
                "--poll-interval",
                "0.05",
            )
            try:
                code_line = sender.stdout.readline().strip()
                self.assertIn("Scrambify code is:", code_line)
                code = code_line.rsplit(": ", 1)[1]

                receiver = self._spawn(
                    "receive",
                    code,
                    "--timeout",
                    "10",
                    "--poll-interval",
                    "0.05",
                    cwd=receiver_dir,
                )
                try:
                    receiver_stdout, receiver_stderr = receiver.communicate(timeout=15)
                finally:
                    if receiver.poll() is None:
                        receiver.kill()
                sender_stdout_rest, sender_stderr = sender.communicate(timeout=15)
            finally:
                if sender.poll() is None:
                    sender.kill()

            saved_path = receiver_dir / source_path.name
            sender_stdout = "\n".join(part for part in [code_line, sender_stdout_rest.strip()] if part)
            self.assertEqual(sender.returncode, 0, msg=sender_stderr)
            self.assertEqual(receiver.returncode, 0, msg=receiver_stderr)
            self.assertEqual(saved_path.read_text(encoding="utf-8"), payload)
            self.assertIn("sent file source.txt", sender_stdout)
            self.assertIn(f"received file source.txt ({saved_path.stat().st_size} bytes) -> {saved_path.resolve()}", receiver_stdout)

    def test_text_transfer_via_cli_processes(self) -> None:
        payload = "hello through the relay"
        sender = self._spawn(
            "send",
            "--text",
            payload,
            "--timeout",
            "10",
            "--poll-interval",
            "0.05",
        )
        try:
            code_line = sender.stdout.readline().strip()
            self.assertIn("Scrambify code is:", code_line)
            code = code_line.rsplit(": ", 1)[1]

            receiver = self._spawn(
                "receive",
                code,
                "--timeout",
                "10",
                "--poll-interval",
                "0.05",
            )
            try:
                receiver_stdout, receiver_stderr = receiver.communicate(timeout=15)
            finally:
                if receiver.poll() is None:
                    receiver.kill()
            sender_stdout_rest, sender_stderr = sender.communicate(timeout=15)
        finally:
            if sender.poll() is None:
                sender.kill()

        sender_stdout = "\n".join(part for part in [code_line, sender_stdout_rest.strip()] if part)
        self.assertEqual(sender.returncode, 0, msg=sender_stderr)
        self.assertEqual(receiver.returncode, 0, msg=receiver_stderr)
        self.assertIn("sent text message", sender_stdout)
        self.assertIn(payload, receiver_stdout)

    def _spawn(self, *args: str, cwd: Path | None = None) -> subprocess.Popen[str]:
        env = os.environ.copy()
        env["SCRAMBIFY_RENDEZVOUS_URL"] = self.base_url
        existing_pythonpath = env.get("PYTHONPATH")
        src_path = str(PROJECT_ROOT / "src")
        env["PYTHONPATH"] = src_path if not existing_pythonpath else os.pathsep.join([src_path, existing_pythonpath])
        return subprocess.Popen(
            [sys.executable, "-m", "scrambify", *args],
            cwd=cwd or PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )