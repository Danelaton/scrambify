from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class RelayConfig:
    rendezvous_url: str
    transit_url: str


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_name: str
    relay: RelayConfig
    code_word_count: int

    @classmethod
    def default(cls) -> "AppConfig":
        return cls(
            app_name="scrambify",
            relay=RelayConfig(
                rendezvous_url=os.environ.get("SCRAMBIFY_RENDEZVOUS_URL", "http://127.0.0.1:4000/v1"),
                transit_url=os.environ.get("SCRAMBIFY_TRANSIT_URL", "tcp://transit.example.invalid:4001"),
            ),
            code_word_count=int(os.environ.get("SCRAMBIFY_CODE_WORD_COUNT", "2")),
        )