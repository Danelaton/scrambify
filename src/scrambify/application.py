from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import time
from typing import Callable
from urllib.parse import urlparse

from scrambify.config import AppConfig
from scrambify.domain.models import ScrambifyCode, SessionRole, TransferDecision, TransferKind, TransferOffer
from scrambify.protocol.mailbox import MemoryMailboxStore
from scrambify.protocol.relay import RelayMailboxStore
from scrambify.services.session import SessionOrchestrator


@dataclass(slots=True)
class ScrambifyApp:
    config: AppConfig
    sessions: SessionOrchestrator

    def send_text(
        self,
        text: str,
        *,
        reporter: Callable[[str], None] | None = None,
        timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 0.25,
    ) -> str:
        payload = text.encode("utf-8")
        code = self.sessions.create_code(self.config.code_word_count)
        offer = TransferOffer(
            kind=TransferKind.TEXT,
            name="message.txt",
            size=len(payload),
            sha256_hex=sha256(payload).hexdigest(),
            chunk_size=65536,
        )
        session = self.sessions.start(role=SessionRole.SENDER, code=code, offer=offer)
        self._report(reporter, f"Scrambify code is: {code.render()}")
        self._report(reporter, "Waiting for the receiver to join...")
        self._poll(
            lambda: self.sessions.establish_shared_keys(session.session_id),
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            description="the receiver to join",
        )
        self._report(reporter, "Receiver connected. Sending text offer...")
        self.sessions.publish_offer(session.session_id)
        response = self._poll(
            lambda: self.sessions.read_response(session.session_id),
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            description="the receiver to accept the offer",
        )
        if response.decision is not TransferDecision.ACCEPT:
            return f"transfer rejected: {response.reason or 'receiver declined the transfer'}"
        self.sessions.send_payload(session.session_id, payload)
        return f"sent text message ({offer.size} bytes) with code {code.render()}"

    def send_file(
        self,
        file_path: str,
        *,
        reporter: Callable[[str], None] | None = None,
        timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 0.25,
    ) -> str:
        path = Path(file_path)
        payload = path.read_bytes()
        code = self.sessions.create_code(self.config.code_word_count)
        offer = TransferOffer(
            kind=TransferKind.FILE,
            name=path.name,
            size=len(payload),
            sha256_hex=sha256(payload).hexdigest(),
            chunk_size=65536,
        )
        session = self.sessions.start(role=SessionRole.SENDER, code=code, offer=offer)
        self._report(reporter, f"Scrambify code is: {code.render()}")
        self._report(reporter, f"Waiting for the receiver to accept {offer.name}...")
        self._poll(
            lambda: self.sessions.establish_shared_keys(session.session_id),
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            description="the receiver to join",
        )
        self._report(reporter, f"Receiver connected. Sending file offer for {offer.name}...")
        self.sessions.publish_offer(session.session_id)
        response = self._poll(
            lambda: self.sessions.read_response(session.session_id),
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            description="the receiver to accept the offer",
        )
        if response.decision is not TransferDecision.ACCEPT:
            return f"transfer rejected for {offer.name}: {response.reason or 'receiver declined the transfer'}"
        self.sessions.send_payload(session.session_id, payload)
        return f"sent file {offer.name} ({offer.size} bytes) with code {code.render()}"

    def receive(
        self,
        code: str,
        *,
        output_path: str | None = None,
        reporter: Callable[[str], None] | None = None,
        timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 0.25,
    ) -> str:
        parsed = ScrambifyCode.parse(code)
        session = self.sessions.start(role=SessionRole.RECEIVER, code=parsed, offer=None)
        self._report(reporter, f"Joined scrambify code {parsed.render()}.")
        self._report(reporter, "Waiting for the sender...")
        self._poll(
            lambda: self.sessions.establish_shared_keys(session.session_id),
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            description="the sender to join",
        )
        offer = self._poll(
            lambda: self.sessions.read_offer(session.session_id),
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            description="the sender's transfer offer",
        )
        if offer.kind is TransferKind.FILE:
            destination = self._resolve_output_path(output_path, offer.name)
            self._report(reporter, f"Accepting file offer for {offer.name}...")
            self.sessions.respond_to_offer(session.session_id, accept=True, save_as=str(destination))
            received = self._poll(
                lambda: self.sessions.receive_payload(session.session_id),
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                description="the file payload",
            )
            destination.write_bytes(received.payload)
            return f"received file {offer.name} ({offer.size} bytes) -> {destination}"

        if offer.kind is TransferKind.TEXT:
            self._report(reporter, "Accepting text offer...")
            self.sessions.respond_to_offer(session.session_id, accept=True)
            received = self._poll(
                lambda: self.sessions.receive_payload(session.session_id),
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                description="the text payload",
            )
            text = received.payload.decode("utf-8")
            if output_path is not None:
                destination = self._resolve_output_path(output_path, offer.name)
                destination.write_text(text, encoding="utf-8", newline="")
                return f"received text message ({offer.size} bytes) -> {destination}"
            return f"received text message ({offer.size} bytes):\n{text}"

        raise ValueError(f"unsupported transfer kind: {offer.kind.value}")

    def _poll(
        self,
        operation: Callable[[], object],
        *,
        timeout_seconds: float,
        poll_interval_seconds: float,
        description: str,
    ) -> object:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                return operation()
            except LookupError as error:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out while waiting for {description}") from error
                time.sleep(poll_interval_seconds)

    def _resolve_output_path(self, output_path: str | None, offered_name: str) -> Path:
        if output_path is None:
            path = Path.cwd() / offered_name
        else:
            candidate = Path(output_path).expanduser()
            looks_like_directory = output_path.endswith(("/", "\\"))
            path = candidate / offered_name if looks_like_directory or (candidate.exists() and candidate.is_dir()) else candidate
        parent = path.parent
        if not parent.exists():
            raise ValueError(f"output directory does not exist: {parent.resolve()}")
        return path.resolve()

    def _report(self, reporter: Callable[[str], None] | None, message: str) -> None:
        if reporter is not None:
            reporter(message)


def build_app() -> ScrambifyApp:
    config = AppConfig.default()
    rendezvous_url = urlparse(config.relay.rendezvous_url)
    if rendezvous_url.scheme in {"memory", ""}:
        mailbox_store = MemoryMailboxStore()
    elif rendezvous_url.scheme in {"http", "https"}:
        mailbox_store = RelayMailboxStore(config.relay.rendezvous_url)
    else:
        raise ValueError(f"unsupported rendezvous relay scheme: {rendezvous_url.scheme}")
    sessions = SessionOrchestrator(mailbox_store=mailbox_store)
    return ScrambifyApp(config=config, sessions=sessions)