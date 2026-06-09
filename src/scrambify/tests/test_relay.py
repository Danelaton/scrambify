from __future__ import annotations

import threading
import time
import unittest

from scrambify.domain.models import ScrambifyCode, SessionRole, TransferKind, TransferOffer
from scrambify.protocol.relay import RelayMailboxStore
from scrambify.services.session import SessionOrchestrator


class RelayIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from scrambify.protocol.relay import RelayRequestHandler
        from http.server import ThreadingHTTPServer

        cls._server = ThreadingHTTPServer(("127.0.0.1", 0), RelayRequestHandler)
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        cls._base_url = f"http://127.0.0.1:{cls._server.server_port}/v1"
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._server.shutdown()
        cls._server.server_close()
        cls._thread.join(timeout=2)

    def test_sender_and_receiver_share_real_relay_mailbox(self) -> None:
        sessions = SessionOrchestrator(mailbox_store=RelayMailboxStore(self._base_url))
        code = ScrambifyCode(nameplate=902, words=("crimson", "bridge"))
        offer = TransferOffer(kind=TransferKind.TEXT, name="message.txt", size=5)

        sender = sessions.start(role=SessionRole.SENDER, code=code, offer=offer)
        receiver = sessions.start(role=SessionRole.RECEIVER, code=code, offer=None)

        sender_messages = sessions.read_mailbox(sender.session_id)
        receiver_messages = sessions.read_mailbox(receiver.session_id)

        self.assertEqual(sender.mailbox_id, receiver.mailbox_id)
        self.assertEqual([message.event for message in sender_messages], ["hello", "hello"])
        self.assertEqual([message.sequence for message in receiver_messages], [1, 2])