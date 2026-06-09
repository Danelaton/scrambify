from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Lock
from urllib import parse, request
from urllib.error import HTTPError, URLError

from scrambify.domain.models import SessionRole
from scrambify.protocol.mailbox import MailboxEnvelope, MailboxProtocol, RendezvousMailbox, mailbox_id_for_nameplate


class RelayError(RuntimeError):
    pass


class RelaySequenceConflict(RelayError):
    def __init__(self, expected_sequence: int) -> None:
        super().__init__(f"relay expected sequence {expected_sequence}")
        self.expected_sequence = expected_sequence


class RelayMailbox(RendezvousMailbox):
    def __init__(self, mailbox_id: str, store: "RelayMailboxStore") -> None:
        self.mailbox_id = mailbox_id
        self._store = store
        self._last_sequence = 0

    def post(
        self,
        *,
        phase: str,
        sender: SessionRole,
        event: str,
        body: dict[str, object],
        mac_key: bytes | None = None,
    ) -> MailboxEnvelope:
        next_sequence = self._last_sequence + 1
        for _ in range(5):
            envelope = self._store.protocol.make_envelope(
                mailbox_id=self.mailbox_id,
                phase=phase,
                sender=sender,
                event=event,
                sequence=next_sequence,
                body=body,
                mac_key=mac_key,
            )
            try:
                response = self._store._request_json(
                    method="POST",
                    path=f"/mailboxes/{parse.quote(self.mailbox_id)}/messages",
                    body=self._store.protocol.envelope_body(envelope),
                    expected_status=HTTPStatus.CREATED,
                )
                accepted = self._store.protocol.parse_envelope(response)
                self._last_sequence = accepted.sequence
                return accepted
            except RelaySequenceConflict as error:
                next_sequence = error.expected_sequence
        raise RelayError(f"failed to post message to relay mailbox {self.mailbox_id}")

    def read(self, after_sequence: int = 0) -> tuple[MailboxEnvelope, ...]:
        response = self._store._request_json(
            method="GET",
            path=f"/mailboxes/{parse.quote(self.mailbox_id)}/messages?after_sequence={after_sequence}",
            expected_status=HTTPStatus.OK,
        )
        messages = tuple(self._store.protocol.parse_envelope(item) for item in response["messages"])
        if messages:
            self._last_sequence = max(self._last_sequence, messages[-1].sequence)
        return messages


class RelayMailboxStore:
    def __init__(self, base_url: str, protocol: MailboxProtocol | None = None, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._protocol = protocol or MailboxProtocol()
        self._timeout_seconds = timeout_seconds

    @property
    def protocol(self) -> MailboxProtocol:
        return self._protocol

    def open_nameplate(self, nameplate: int) -> RelayMailbox:
        response = self._request_json(
            method="POST",
            path=f"/nameplates/{nameplate}/open",
            body={},
            expected_status=HTTPStatus.OK,
        )
        return RelayMailbox(mailbox_id=str(response["mailbox_id"]), store=self)

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        expected_status: HTTPStatus,
    ) -> dict[str, object]:
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        relay_request = request.Request(
            url=f"{self._base_url}{path}",
            data=payload,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(relay_request, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
                if response.status != expected_status:
                    raise RelayError(f"unexpected relay status {response.status}: {data}")
                return data
        except HTTPError as error:
            raw = error.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            if error.code == HTTPStatus.CONFLICT and "expected_sequence" in data:
                raise RelaySequenceConflict(int(data["expected_sequence"])) from error
            detail = data.get("error", raw or error.reason)
            raise RelayError(f"relay request failed with status {error.code}: {detail}") from error
        except URLError as error:
            raise RelayError(f"could not reach relay at {self._base_url}: {error.reason}") from error


class RelayMailboxRepository:
    def __init__(self, protocol: MailboxProtocol | None = None) -> None:
        self._protocol = protocol or MailboxProtocol()
        self._mailboxes: dict[str, list[MailboxEnvelope]] = {}
        self._lock = Lock()

    def open_nameplate(self, nameplate: int) -> str:
        mailbox_id = mailbox_id_for_nameplate(nameplate)
        with self._lock:
            self._mailboxes.setdefault(mailbox_id, [])
        return mailbox_id

    def read_messages(self, mailbox_id: str, after_sequence: int) -> tuple[MailboxEnvelope, ...]:
        with self._lock:
            messages = self._mailboxes.get(mailbox_id)
            if messages is None:
                raise KeyError(mailbox_id)
            return tuple(message for message in messages if message.sequence > after_sequence)

    def append_message(self, mailbox_id: str, envelope_body: dict[str, object]) -> MailboxEnvelope:
        envelope = self._protocol.parse_envelope(envelope_body)
        if envelope.mailbox_id != mailbox_id:
            raise ValueError("mailbox_id in payload did not match request path")
        with self._lock:
            messages = self._mailboxes.get(mailbox_id)
            if messages is None:
                raise KeyError(mailbox_id)
            expected_sequence = len(messages) + 1
            if envelope.sequence != expected_sequence:
                raise RelaySequenceConflict(expected_sequence)
            messages.append(envelope)
            return envelope


class RelayRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    repository = RelayMailboxRepository()

    def do_POST(self) -> None:
        parsed = parse.urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 4 and parts[0] == "v1" and parts[1] == "nameplates" and parts[3] == "open":
            self._read_json_body()
            try:
                nameplate = int(parts[2])
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "nameplate must be numeric"})
                return
            mailbox_id = self.repository.open_nameplate(nameplate)
            self._send_json(HTTPStatus.OK, {"mailbox_id": mailbox_id})
            return

        if len(parts) == 4 and parts[0] == "v1" and parts[1] == "mailboxes" and parts[3] == "messages":
            mailbox_id = parse.unquote(parts[2])
            payload = self._read_json_body()
            try:
                envelope = self.repository.append_message(mailbox_id, payload)
            except KeyError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"unknown mailbox {mailbox_id}"})
                return
            except RelaySequenceConflict as error:
                self._send_json(HTTPStatus.CONFLICT, {"error": str(error), "expected_sequence": error.expected_sequence})
                return
            except ValueError as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            self._send_json(HTTPStatus.CREATED, self.repository._protocol.envelope_body(envelope))
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})

    def do_GET(self) -> None:
        parsed = parse.urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 4 and parts[0] == "v1" and parts[1] == "mailboxes" and parts[3] == "messages":
            mailbox_id = parse.unquote(parts[2])
            query = parse.parse_qs(parsed.query)
            try:
                after_sequence = int(query.get("after_sequence", ["0"])[0])
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "after_sequence must be numeric"})
                return
            try:
                messages = self.repository.read_messages(mailbox_id, after_sequence)
            except KeyError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"unknown mailbox {mailbox_id}"})
                return
            self._send_json(
                HTTPStatus.OK,
                {"messages": [self.repository._protocol.envelope_body(message) for message in messages]},
            )
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> dict[str, object]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_relay_server(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), RelayRequestHandler)
    address = f"http://{host}:{port}/v1"
    print(f"relay server listening on {address}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()