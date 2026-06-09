from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256, scrypt
import hmac
import secrets

from scrambify.domain.models import ScrambifyCode, SessionRole


def _hkdf_extract(salt: bytes, input_key_material: bytes) -> bytes:
    return hmac.new(salt, input_key_material, sha256).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    output = bytearray()
    previous = b""
    counter = 1
    while len(output) < length:
        previous = hmac.new(prk, previous + info + bytes([counter]), sha256).digest()
        output.extend(previous)
        counter += 1
    return bytes(output[:length])


def _derive_code_key(code: ScrambifyCode) -> bytes:
    salt = f"scrambify:{code.nameplate}".encode("utf-8")
    password = code.render().encode("utf-8")
    return scrypt(password=password, salt=salt, n=1 << 14, r=8, p=1, dklen=32)


def _session_transcript(mailbox_id: str, sender_nonce: bytes, receiver_nonce: bytes) -> bytes:
    return b"|".join([mailbox_id.encode("utf-8"), sender_nonce.hex().encode("ascii"), receiver_nonce.hex().encode("ascii")])


@dataclass(frozen=True, slots=True)
class PakeHello:
    role: SessionRole
    nonce_hex: str
    commitment_hex: str

    def to_body(self) -> dict[str, str]:
        return {
            "role": self.role.value,
            "nonce": self.nonce_hex,
            "commitment": self.commitment_hex,
        }

    @classmethod
    def from_body(cls, body: dict[str, str]) -> "PakeHello":
        return cls(
            role=SessionRole(body["role"]),
            nonce_hex=body["nonce"],
            commitment_hex=body["commitment"],
        )


@dataclass(frozen=True, slots=True)
class PakeConfirmation:
    role: SessionRole
    authenticator_hex: str

    def to_body(self) -> dict[str, str]:
        return {
            "role": self.role.value,
            "authenticator": self.authenticator_hex,
        }

    @classmethod
    def from_body(cls, body: dict[str, str]) -> "PakeConfirmation":
        return cls(role=SessionRole(body["role"]), authenticator_hex=body["authenticator"])


@dataclass(frozen=True, slots=True)
class SharedKeySet:
    session_key: bytes
    mailbox_key: bytes
    confirmation_key: bytes
    verifier_hex: str


class PakeParty:
    def __init__(self, role: SessionRole, code: ScrambifyCode, mailbox_id: str, nonce: bytes | None = None) -> None:
        self._role = role
        self._code = code
        self._mailbox_id = mailbox_id
        self._nonce = nonce or secrets.token_bytes(16)
        self._code_key = _derive_code_key(code)

    @property
    def role(self) -> SessionRole:
        return self._role

    def create_hello(self) -> PakeHello:
        transcript = b"|".join(
            [
                b"hello",
                self._mailbox_id.encode("utf-8"),
                self._role.value.encode("utf-8"),
                self._nonce.hex().encode("ascii"),
            ]
        )
        commitment = hmac.new(self._code_key, transcript, sha256).hexdigest()
        return PakeHello(role=self._role, nonce_hex=self._nonce.hex(), commitment_hex=commitment)

    def finalize(self, peer_hello: PakeHello) -> SharedKeySet:
        if peer_hello.role == self._role:
            raise ValueError("peer hello must come from the opposite role")
        peer_nonce = bytes.fromhex(peer_hello.nonce_hex)
        expected_commitment = hmac.new(
            self._code_key,
            b"|".join(
                [
                    b"hello",
                    self._mailbox_id.encode("utf-8"),
                    peer_hello.role.value.encode("utf-8"),
                    peer_hello.nonce_hex.encode("ascii"),
                ]
            ),
            sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_commitment, peer_hello.commitment_hex):
            raise ValueError("peer hello commitment did not match the shared scrambify code")

        if self._role == SessionRole.SENDER:
            sender_nonce = self._nonce
            receiver_nonce = peer_nonce
        else:
            sender_nonce = peer_nonce
            receiver_nonce = self._nonce

        transcript = _session_transcript(self._mailbox_id, sender_nonce=sender_nonce, receiver_nonce=receiver_nonce)
        prk = _hkdf_extract(self._code_key, transcript)
        session_key = _hkdf_expand(prk, b"session-key", 32)
        mailbox_key = _hkdf_expand(prk, b"mailbox-key", 32)
        confirmation_key = _hkdf_expand(prk, b"confirmation-key", 32)
        verifier_hex = sha256(session_key + mailbox_key).hexdigest()
        return SharedKeySet(
            session_key=session_key,
            mailbox_key=mailbox_key,
            confirmation_key=confirmation_key,
            verifier_hex=verifier_hex,
        )

    def create_confirmation(self, keys: SharedKeySet) -> PakeConfirmation:
        authenticator = hmac.new(
            keys.confirmation_key,
            b"|".join(
                [
                    self._mailbox_id.encode("utf-8"),
                    self._role.value.encode("utf-8"),
                    keys.verifier_hex.encode("ascii"),
                ]
            ),
            sha256,
        ).hexdigest()
        return PakeConfirmation(role=self._role, authenticator_hex=authenticator)

    def verify_confirmation(self, peer_confirmation: PakeConfirmation, keys: SharedKeySet) -> None:
        expected = hmac.new(
            keys.confirmation_key,
            b"|".join(
                [
                    self._mailbox_id.encode("utf-8"),
                    peer_confirmation.role.value.encode("utf-8"),
                    keys.verifier_hex.encode("ascii"),
                ]
            ),
            sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, peer_confirmation.authenticator_hex):
            raise ValueError("peer confirmation failed for the derived shared keys")