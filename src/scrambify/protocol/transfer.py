from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import secrets

from scrambify.domain.models import TransferDecision, TransferKind, TransferOffer, TransferResponse


def _derive_key(session_key: bytes, label: bytes) -> bytes:
    return hmac.new(session_key, b"scrambify-transfer|" + label, sha256).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks = bytearray()
    counter = 0
    while len(blocks) < length:
        counter_bytes = counter.to_bytes(4, "big")
        blocks.extend(hmac.new(key, nonce + counter_bytes, sha256).digest())
        counter += 1
    return bytes(blocks[:length])


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(left_byte ^ right_byte for left_byte, right_byte in zip(left, right))


def _decode_json_dict(data: bytes) -> dict[str, object]:
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("encrypted transfer message must decode to a JSON object")
    return value


@dataclass(frozen=True, slots=True)
class FileChunk:
    index: int
    total: int
    offset: int
    payload: bytes
    sha256_hex: str


class FileTransferProtocol:
    def __init__(self, session_key: bytes) -> None:
        self._control_key = _derive_key(session_key, b"control")
        self._data_key = _derive_key(session_key, b"data")

    def _seal(self, payload: dict[str, object], key: bytes) -> dict[str, str]:
        plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        nonce = secrets.token_bytes(16)
        ciphertext = _xor_bytes(plaintext, _keystream(key, nonce, len(plaintext)))
        mac_hex = hmac.new(key, nonce + ciphertext, sha256).hexdigest()
        return {
            "nonce": urlsafe_b64encode(nonce).decode("ascii"),
            "ciphertext": urlsafe_b64encode(ciphertext).decode("ascii"),
            "mac": mac_hex,
        }

    def _open(self, body: dict[str, object], key: bytes) -> dict[str, object]:
        nonce = urlsafe_b64decode(str(body["nonce"]).encode("ascii"))
        ciphertext = urlsafe_b64decode(str(body["ciphertext"]).encode("ascii"))
        mac_hex = str(body["mac"])
        expected_mac = hmac.new(key, nonce + ciphertext, sha256).hexdigest()
        if not hmac.compare_digest(expected_mac, mac_hex):
            raise ValueError("encrypted transfer message authentication failed")
        plaintext = _xor_bytes(ciphertext, _keystream(key, nonce, len(ciphertext)))
        return _decode_json_dict(plaintext)

    def offer_body(self, offer: TransferOffer) -> dict[str, str]:
        return self._seal(
            {
                "kind": offer.kind.value,
                "name": offer.name,
                "size": offer.size,
                "sha256": offer.sha256_hex,
                "chunk_size": offer.chunk_size,
            },
            self._control_key,
        )

    def parse_offer(self, body: dict[str, object]) -> TransferOffer:
        payload = self._open(body, self._control_key)
        return TransferOffer(
            kind=TransferKind(str(payload["kind"])),
            name=str(payload["name"]),
            size=int(payload["size"]),
            sha256_hex=None if payload["sha256"] is None else str(payload["sha256"]),
            chunk_size=None if payload["chunk_size"] is None else int(payload["chunk_size"]),
        )

    def response_body(self, response: TransferResponse) -> dict[str, str]:
        return self._seal(
            {
                "decision": response.decision.value,
                "save_as": response.save_as,
                "reason": response.reason,
            },
            self._control_key,
        )

    def parse_response(self, body: dict[str, object]) -> TransferResponse:
        payload = self._open(body, self._control_key)
        return TransferResponse(
            decision=TransferDecision(str(payload["decision"])),
            save_as=None if payload["save_as"] is None else str(payload["save_as"]),
            reason=None if payload["reason"] is None else str(payload["reason"]),
        )

    def chunk_body(self, *, index: int, total: int, offset: int, payload: bytes) -> dict[str, str]:
        return self._seal(
            {
                "index": index,
                "total": total,
                "offset": offset,
                "payload": urlsafe_b64encode(payload).decode("ascii"),
                "sha256": sha256(payload).hexdigest(),
            },
            self._data_key,
        )

    def parse_chunk(self, body: dict[str, object]) -> FileChunk:
        payload = self._open(body, self._data_key)
        chunk_payload = urlsafe_b64decode(str(payload["payload"]).encode("ascii"))
        chunk_sha256 = sha256(chunk_payload).hexdigest()
        if chunk_sha256 != str(payload["sha256"]):
            raise ValueError("file chunk checksum did not match decrypted payload")
        return FileChunk(
            index=int(payload["index"]),
            total=int(payload["total"]),
            offset=int(payload["offset"]),
            payload=chunk_payload,
            sha256_hex=chunk_sha256,
        )