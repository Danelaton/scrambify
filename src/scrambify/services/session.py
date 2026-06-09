from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import count

from scrambify.domain.models import ReceivedTransfer, ScrambifyCode, SessionRole, TransferDecision, TransferKind, TransferOffer, TransferResponse
from scrambify.protocol.mailbox import MailboxEnvelope, RendezvousMailbox, RendezvousMailboxStore
from scrambify.protocol.pake import PakeParty, SharedKeySet
from scrambify.protocol.transfer import FileTransferProtocol
from scrambify.services.codes import CodeGenerator


@dataclass(frozen=True, slots=True)
class SessionHandle:
    session_id: str
    role: SessionRole
    code: ScrambifyCode
    offer: TransferOffer | None
    mailbox_id: str
    local_sequence: int


@dataclass(slots=True)
class _SessionState:
    handle: SessionHandle
    mailbox: RendezvousMailbox
    handshake: PakeParty
    shared_keys: SharedKeySet | None = None
    transfer: FileTransferProtocol | None = None


class SessionOrchestrator:
    def __init__(self, code_generator: CodeGenerator | None = None, mailbox_store: RendezvousMailboxStore | None = None) -> None:
        self._sequence = count(start=1)
        self._code_generator = code_generator or CodeGenerator()
        from scrambify.protocol.mailbox import MemoryMailboxStore

        self._mailboxes = mailbox_store or MemoryMailboxStore()
        self._sessions: dict[str, _SessionState] = {}

    def create_code(self, word_count: int) -> ScrambifyCode:
        return self._code_generator.generate(word_count)

    def start(self, role: SessionRole, code: ScrambifyCode, offer: TransferOffer | None) -> SessionHandle:
        session_number = next(self._sequence)
        session_id = f"session-{session_number:04d}"
        mailbox = self._mailboxes.open_nameplate(code.nameplate)
        handshake = PakeParty(role=role, code=code, mailbox_id=mailbox.mailbox_id)
        hello = handshake.create_hello()
        hello_envelope = mailbox.post(
            phase="pake",
            sender=role,
            event="hello",
            body=self._mailboxes.protocol.hello_body(hello),
        )
        handle = SessionHandle(
            session_id=session_id,
            role=role,
            code=code,
            offer=offer,
            mailbox_id=mailbox.mailbox_id,
            local_sequence=hello_envelope.sequence,
        )
        self._sessions[session_id] = _SessionState(handle=handle, mailbox=mailbox, handshake=handshake)
        return handle

    def read_mailbox(self, session_id: str, after_sequence: int = 0) -> tuple[MailboxEnvelope, ...]:
        state = self._require_state(session_id)
        return state.mailbox.read(after_sequence=after_sequence)

    def establish_shared_keys(self, session_id: str) -> SharedKeySet:
        state = self._require_state(session_id)
        if state.shared_keys is not None:
            return state.shared_keys

        peer_hello = None
        for envelope in state.mailbox.read():
            if envelope.phase != "pake" or envelope.event != "hello":
                continue
            if envelope.sender == state.handle.role.value:
                continue
            peer_hello = self._mailboxes.protocol.parse_hello(envelope)
            break

        if peer_hello is None:
            raise LookupError("peer hello is not yet present in the rendezvous mailbox")

        keys = state.handshake.finalize(peer_hello)
        confirmation = state.handshake.create_confirmation(keys)
        state.mailbox.post(
            phase="pake",
            sender=state.handle.role,
            event="confirm",
            body=self._mailboxes.protocol.confirmation_body(confirmation),
            mac_key=keys.mailbox_key,
        )
        state.shared_keys = keys
        return keys

    def publish_offer(self, session_id: str) -> MailboxEnvelope:
        state = self._require_state(session_id)
        if state.handle.offer is None:
            raise ValueError("only sender sessions can publish a transfer offer")
        transfer, keys = self._require_transfer(state)
        return state.mailbox.post(
            phase="transfer",
            sender=state.handle.role,
            event="offer",
            body=transfer.offer_body(state.handle.offer),
            mac_key=keys.mailbox_key,
        )

    def read_offer(self, session_id: str) -> TransferOffer:
        state = self._require_state(session_id)
        transfer, keys = self._require_transfer(state)
        for envelope in state.mailbox.read():
            if envelope.phase != "transfer" or envelope.event != "offer":
                continue
            if envelope.sender == state.handle.role.value:
                continue
            self._mailboxes.protocol.verify(envelope, keys.mailbox_key)
            return transfer.parse_offer(envelope.body)
        raise LookupError("peer transfer offer is not yet present in the rendezvous mailbox")

    def respond_to_offer(
        self,
        session_id: str,
        *,
        accept: bool,
        save_as: str | None = None,
        reason: str | None = None,
    ) -> MailboxEnvelope:
        state = self._require_state(session_id)
        if state.handle.role is not SessionRole.RECEIVER:
            raise ValueError("only receiver sessions can respond to a transfer offer")
        transfer, keys = self._require_transfer(state)
        response = TransferResponse(
            decision=TransferDecision.ACCEPT if accept else TransferDecision.REJECT,
            save_as=save_as,
            reason=reason if not accept else None,
        )
        return state.mailbox.post(
            phase="transfer",
            sender=state.handle.role,
            event="response",
            body=transfer.response_body(response),
            mac_key=keys.mailbox_key,
        )

    def read_response(self, session_id: str) -> TransferResponse:
        state = self._require_state(session_id)
        transfer, keys = self._require_transfer(state)
        for envelope in state.mailbox.read():
            if envelope.phase != "transfer" or envelope.event != "response":
                continue
            if envelope.sender == state.handle.role.value:
                continue
            self._mailboxes.protocol.verify(envelope, keys.mailbox_key)
            return transfer.parse_response(envelope.body)
        raise LookupError("peer transfer response is not yet present in the rendezvous mailbox")

    def send_payload(self, session_id: str, payload: bytes) -> tuple[MailboxEnvelope, ...]:
        state = self._require_state(session_id)
        if state.handle.offer is None or state.handle.role is not SessionRole.SENDER:
            raise ValueError("only sender sessions can stream transfer payloads")
        if state.handle.offer.kind not in {TransferKind.FILE, TransferKind.TEXT}:
            raise ValueError("only text and file transfer sessions can stream payloads")
        response = self.read_response(session_id)
        if response.decision is not TransferDecision.ACCEPT:
            raise ValueError("receiver did not accept the transfer offer")
        expected_digest = sha256(payload).hexdigest()
        if len(payload) != state.handle.offer.size:
            raise ValueError("transfer payload length does not match the advertised transfer offer")
        if state.handle.offer.sha256_hex is not None and expected_digest != state.handle.offer.sha256_hex:
            raise ValueError("transfer payload checksum does not match the advertised transfer offer")

        transfer, keys = self._require_transfer(state)
        chunk_size = state.handle.offer.chunk_size or 65536
        total_chunks = max(1, (len(payload) + chunk_size - 1) // chunk_size)
        envelopes: list[MailboxEnvelope] = []
        for index in range(total_chunks):
            offset = index * chunk_size
            chunk = payload[offset : offset + chunk_size]
            envelopes.append(
                state.mailbox.post(
                    phase="transfer",
                    sender=state.handle.role,
                    event="file-chunk",
                    body=transfer.chunk_body(index=index, total=total_chunks, offset=offset, payload=chunk),
                    mac_key=keys.mailbox_key,
                )
            )
        return tuple(envelopes)

    def send_file_data(self, session_id: str, payload: bytes) -> tuple[MailboxEnvelope, ...]:
        state = self._require_state(session_id)
        if state.handle.offer is None or state.handle.offer.kind is not TransferKind.FILE:
            raise ValueError("only sender file-transfer sessions can stream file payloads")
        return self.send_payload(session_id, payload)

    def receive_payload(self, session_id: str) -> ReceivedTransfer:
        state = self._require_state(session_id)
        transfer_offer = self.read_offer(session_id)
        if transfer_offer.kind not in {TransferKind.FILE, TransferKind.TEXT}:
            raise ValueError("peer transfer offer is not a text or file transfer")

        transfer, keys = self._require_transfer(state)
        chunks = []
        for envelope in state.mailbox.read():
            if envelope.phase != "transfer" or envelope.event != "file-chunk":
                continue
            if envelope.sender == state.handle.role.value:
                continue
            self._mailboxes.protocol.verify(envelope, keys.mailbox_key)
            chunks.append(transfer.parse_chunk(envelope.body))

        if not chunks:
            raise LookupError("no transfer payload chunks are available in the rendezvous mailbox")

        ordered_chunks = sorted(chunks, key=lambda chunk: chunk.index)
        expected_total = ordered_chunks[0].total
        actual_indexes = [chunk.index for chunk in ordered_chunks]
        expected_prefix = list(range(len(actual_indexes)))
        if actual_indexes != expected_prefix:
            raise ValueError("file payload chunks are missing or out of order")
        if len(ordered_chunks) < expected_total:
            raise LookupError("transfer payload is not yet complete")
        if any(chunk.total != expected_total for chunk in ordered_chunks):
            raise ValueError("file payload chunks do not agree on the advertised chunk count")
        payload = b"".join(chunk.payload for chunk in ordered_chunks)
        if len(payload) != transfer_offer.size:
            raise ValueError("received file payload length does not match the transfer offer")
        payload_digest = sha256(payload).hexdigest()
        if transfer_offer.sha256_hex is not None and payload_digest != transfer_offer.sha256_hex:
            raise ValueError("received file payload checksum does not match the transfer offer")
        return ReceivedTransfer(offer=transfer_offer, payload=payload, sha256_hex=payload_digest)

    def receive_file_data(self, session_id: str) -> ReceivedTransfer:
        state = self._require_state(session_id)
        transfer_offer = self.read_offer(session_id)
        if transfer_offer.kind is not TransferKind.FILE:
            raise ValueError("peer transfer offer is not a file transfer")
        return self.receive_payload(session_id)

    def verify_mailbox(self, session_id: str) -> tuple[MailboxEnvelope, ...]:
        state = self._require_state(session_id)
        keys = self.establish_shared_keys(session_id)
        verified_messages: list[MailboxEnvelope] = []
        for envelope in state.mailbox.read():
            if envelope.phase == "pake" and envelope.event == "hello":
                verified_messages.append(envelope)
                continue
            self._mailboxes.protocol.verify(envelope, keys.mailbox_key)
            verified_messages.append(envelope)
        return tuple(verified_messages)

    def _require_state(self, session_id: str) -> _SessionState:
        try:
            return self._sessions[session_id]
        except KeyError as error:
            raise KeyError(f"unknown session: {session_id}") from error

    def _require_transfer(self, state: _SessionState) -> tuple[FileTransferProtocol, SharedKeySet]:
        keys = self.establish_shared_keys(state.handle.session_id)
        if state.transfer is None:
            state.transfer = FileTransferProtocol(keys.session_key)
        return state.transfer, keys