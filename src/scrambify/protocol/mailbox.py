from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from threading import Lock
from typing import Protocol

from scrambify.domain.models import SessionRole, TransferKind, TransferOffer
from scrambify.protocol.pake import PakeConfirmation, PakeHello


def mailbox_id_for_nameplate(nameplate: int) -> str:
    return f"mailbox-{nameplate}"


@dataclass(frozen=True, slots=True)
class MailboxEnvelope:
    mailbox_id: str
    phase: str
    sender: str
    event: str
    sequence: int
    body: dict[str, object]
    mac_hex: str | None


class RendezvousMailbox(Protocol):
    mailbox_id: str

    def post(
        self,
        *,
        phase: str,
        sender: SessionRole,
        event: str,
        body: dict[str, object],
        mac_key: bytes | None = None,
    ) -> MailboxEnvelope: ...

    def read(self, after_sequence: int = 0) -> tuple[MailboxEnvelope, ...]: ...


class RendezvousMailboxStore(Protocol):
    @property
    def protocol(self) -> "MailboxProtocol": ...

    def open_nameplate(self, nameplate: int) -> RendezvousMailbox: ...


class MailboxProtocol:
    def _canonical_payload(self, envelope: MailboxEnvelope) -> bytes:
        payload = {
            "mailbox_id": envelope.mailbox_id,
            "phase": envelope.phase,
            "sender": envelope.sender,
            "event": envelope.event,
            "sequence": envelope.sequence,
            "body": envelope.body,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def make_envelope(
        self,
        *,
        mailbox_id: str,
        phase: str,
        sender: SessionRole,
        event: str,
        sequence: int,
        body: dict[str, object],
        mac_key: bytes | None = None,
    ) -> MailboxEnvelope:
        envelope = MailboxEnvelope(
            mailbox_id=mailbox_id,
            phase=phase,
            sender=sender.value,
            event=event,
            sequence=sequence,
            body=body,
            mac_hex=None,
        )
        if mac_key is None:
            return envelope
        mac_hex = hmac.new(mac_key, self._canonical_payload(envelope), sha256).hexdigest()
        return MailboxEnvelope(
            mailbox_id=envelope.mailbox_id,
            phase=envelope.phase,
            sender=envelope.sender,
            event=envelope.event,
            sequence=envelope.sequence,
            body=envelope.body,
            mac_hex=mac_hex,
        )

    def verify(self, envelope: MailboxEnvelope, mac_key: bytes) -> None:
        if envelope.mac_hex is None:
            raise ValueError("mailbox envelope is not authenticated")
        expected = hmac.new(mac_key, self._canonical_payload(envelope), sha256).hexdigest()
        if not hmac.compare_digest(expected, envelope.mac_hex):
            raise ValueError("mailbox envelope authentication failed")

    def envelope_body(self, envelope: MailboxEnvelope) -> dict[str, object]:
        return {
            "mailbox_id": envelope.mailbox_id,
            "phase": envelope.phase,
            "sender": envelope.sender,
            "event": envelope.event,
            "sequence": envelope.sequence,
            "body": envelope.body,
            "mac_hex": envelope.mac_hex,
        }

    def parse_envelope(self, body: dict[str, object]) -> MailboxEnvelope:
        return MailboxEnvelope(
            mailbox_id=str(body["mailbox_id"]),
            phase=str(body["phase"]),
            sender=str(body["sender"]),
            event=str(body["event"]),
            sequence=int(body["sequence"]),
            body=dict(body["body"]),
            mac_hex=str(body["mac_hex"]) if body["mac_hex"] is not None else None,
        )

    def hello_body(self, hello: PakeHello) -> dict[str, object]:
        return hello.to_body()

    def parse_hello(self, envelope: MailboxEnvelope) -> PakeHello:
        return PakeHello.from_body({key: str(value) for key, value in envelope.body.items()})

    def confirmation_body(self, confirmation: PakeConfirmation) -> dict[str, object]:
        return confirmation.to_body()

    def parse_confirmation(self, envelope: MailboxEnvelope) -> PakeConfirmation:
        return PakeConfirmation.from_body({key: str(value) for key, value in envelope.body.items()})

    def offer_body(self, offer: TransferOffer) -> dict[str, object]:
        return {
            "kind": offer.kind.value,
            "name": offer.name,
            "size": offer.size,
        }

    def parse_offer(self, envelope: MailboxEnvelope) -> TransferOffer:
        return TransferOffer(
            kind=TransferKind(str(envelope.body["kind"])),
            name=str(envelope.body["name"]),
            size=int(envelope.body["size"]),
        )


class MemoryMailbox:
    def __init__(self, mailbox_id: str, protocol: MailboxProtocol) -> None:
        self.mailbox_id = mailbox_id
        self._protocol = protocol
        self._messages: list[MailboxEnvelope] = []
        self._lock = Lock()

    def post(
        self,
        *,
        phase: str,
        sender: SessionRole,
        event: str,
        body: dict[str, object],
        mac_key: bytes | None = None,
    ) -> MailboxEnvelope:
        with self._lock:
            sequence = len(self._messages) + 1
            envelope = self._protocol.make_envelope(
                mailbox_id=self.mailbox_id,
                phase=phase,
                sender=sender,
                event=event,
                sequence=sequence,
                body=body,
                mac_key=mac_key,
            )
            self._messages.append(envelope)
            return envelope

    def read(self, after_sequence: int = 0) -> tuple[MailboxEnvelope, ...]:
        with self._lock:
            return tuple(message for message in self._messages if message.sequence > after_sequence)


class MemoryMailboxStore:
    def __init__(self, protocol: MailboxProtocol | None = None) -> None:
        self._protocol = protocol or MailboxProtocol()
        self._mailboxes: dict[str, MemoryMailbox] = {}
        self._lock = Lock()

    @property
    def protocol(self) -> MailboxProtocol:
        return self._protocol

    def open_nameplate(self, nameplate: int) -> MemoryMailbox:
        mailbox_id = mailbox_id_for_nameplate(nameplate)
        with self._lock:
            mailbox = self._mailboxes.get(mailbox_id)
            if mailbox is None:
                mailbox = MemoryMailbox(mailbox_id=mailbox_id, protocol=self._protocol)
                self._mailboxes[mailbox_id] = mailbox
            return mailbox