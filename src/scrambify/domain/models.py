from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SessionRole(str, Enum):
    SENDER = "sender"
    RECEIVER = "receiver"


class TransferKind(str, Enum):
    TEXT = "text"
    FILE = "file"
    DIRECTORY = "directory"


class TransferDecision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ScrambifyCode:
    nameplate: int
    words: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.nameplate <= 0:
            raise ValueError("scrambify code nameplate must be positive")
        if not self.words:
            raise ValueError("scrambify code must include at least one word")
        if any((not word) or (not word.isalpha()) for word in self.words):
            raise ValueError("scrambify code words must be alphabetic")

    def render(self) -> str:
        normalized_words = tuple(word.lower() for word in self.words)
        return "-".join([str(self.nameplate), *normalized_words])

    @classmethod
    def parse(cls, raw: str) -> "ScrambifyCode":
        parts = [part.strip() for part in raw.split("-") if part.strip()]
        if len(parts) < 2:
            raise ValueError("scrambify code must include a numeric nameplate and at least one word")
        if not parts[0].isdigit():
            raise ValueError("scrambify code nameplate must be numeric")
        words = tuple(part.lower() for part in parts[1:])
        return cls(nameplate=int(parts[0]), words=words)


@dataclass(frozen=True, slots=True)
class TransferOffer:
    kind: TransferKind
    name: str
    size: int
    sha256_hex: str | None = None
    chunk_size: int | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("transfer offer name must not be empty")
        if self.size < 0:
            raise ValueError("transfer offer size must not be negative")
        if self.sha256_hex is not None:
            if len(self.sha256_hex) != 64 or any(character not in "0123456789abcdef" for character in self.sha256_hex.lower()):
                raise ValueError("transfer offer sha256 must be a 64-character hexadecimal string")
        if self.chunk_size is not None and self.chunk_size <= 0:
            raise ValueError("transfer offer chunk size must be positive")


@dataclass(frozen=True, slots=True)
class TransferResponse:
    decision: TransferDecision
    save_as: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.decision is TransferDecision.ACCEPT and self.reason is not None:
            raise ValueError("accepted transfers must not include a rejection reason")
        if self.decision is TransferDecision.REJECT and self.reason is None:
            raise ValueError("rejected transfers must include a reason")


@dataclass(frozen=True, slots=True)
class ReceivedTransfer:
    offer: TransferOffer
    payload: bytes
    sha256_hex: str