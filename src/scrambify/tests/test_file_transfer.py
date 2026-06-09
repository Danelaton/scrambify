from __future__ import annotations

import unittest
from hashlib import sha256

from scrambify.domain.models import ScrambifyCode, SessionRole, TransferKind, TransferOffer
from scrambify.services.session import SessionOrchestrator


class FileTransferProtocolTests(unittest.TestCase):
    def test_file_transfer_round_trip(self) -> None:
        sessions = SessionOrchestrator()
        code = ScrambifyCode(nameplate=501, words=("amber", "forest"))
        payload = b"scrambify file payload" * 40
        offer = TransferOffer(
            kind=TransferKind.FILE,
            name="payload.bin",
            size=len(payload),
            sha256_hex=sha256(payload).hexdigest(),
            chunk_size=64,
        )

        sender = sessions.start(role=SessionRole.SENDER, code=code, offer=offer)
        receiver = sessions.start(role=SessionRole.RECEIVER, code=code, offer=None)

        sessions.publish_offer(sender.session_id)
        received_offer = sessions.read_offer(receiver.session_id)
        self.assertEqual(received_offer, offer)

        sessions.respond_to_offer(receiver.session_id, accept=True, save_as="payload.bin")
        response = sessions.read_response(sender.session_id)
        self.assertEqual(response.decision.value, "accept")

        chunk_messages = sessions.send_file_data(sender.session_id, payload)
        self.assertGreater(len(chunk_messages), 1)

        received_transfer = sessions.receive_file_data(receiver.session_id)
        self.assertEqual(received_transfer.offer, offer)
        self.assertEqual(received_transfer.payload, payload)
        self.assertEqual(received_transfer.sha256_hex, offer.sha256_hex)

    def test_rejected_file_transfer_blocks_sender_payload(self) -> None:
        sessions = SessionOrchestrator()
        code = ScrambifyCode(nameplate=777, words=("silver", "wave"))
        payload = b"payload"
        offer = TransferOffer(
            kind=TransferKind.FILE,
            name="payload.bin",
            size=len(payload),
            sha256_hex=sha256(payload).hexdigest(),
            chunk_size=4,
        )

        sender = sessions.start(role=SessionRole.SENDER, code=code, offer=offer)
        receiver = sessions.start(role=SessionRole.RECEIVER, code=code, offer=None)

        sessions.publish_offer(sender.session_id)
        sessions.read_offer(receiver.session_id)
        sessions.respond_to_offer(receiver.session_id, accept=False, reason="receiver declined")

        with self.assertRaisesRegex(ValueError, "receiver did not accept the transfer offer"):
            sessions.send_file_data(sender.session_id, payload)

    def test_text_transfer_round_trip(self) -> None:
        sessions = SessionOrchestrator()
        code = ScrambifyCode(nameplate=909, words=("violet", "signal"))
        payload = "hello from scrambify".encode("utf-8")
        offer = TransferOffer(
            kind=TransferKind.TEXT,
            name="message.txt",
            size=len(payload),
            sha256_hex=sha256(payload).hexdigest(),
            chunk_size=8,
        )

        sender = sessions.start(role=SessionRole.SENDER, code=code, offer=offer)
        receiver = sessions.start(role=SessionRole.RECEIVER, code=code, offer=None)

        sessions.publish_offer(sender.session_id)
        received_offer = sessions.read_offer(receiver.session_id)
        self.assertEqual(received_offer, offer)

        sessions.respond_to_offer(receiver.session_id, accept=True)
        response = sessions.read_response(sender.session_id)
        self.assertEqual(response.decision.value, "accept")

        chunk_messages = sessions.send_payload(sender.session_id, payload)
        self.assertGreaterEqual(len(chunk_messages), 1)

        received_transfer = sessions.receive_payload(receiver.session_id)
        self.assertEqual(received_transfer.offer, offer)
        self.assertEqual(received_transfer.payload, payload)
        self.assertEqual(received_transfer.sha256_hex, offer.sha256_hex)


if __name__ == "__main__":
    unittest.main()