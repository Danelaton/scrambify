from __future__ import annotations

import secrets

from scrambify.domain.models import ScrambifyCode


DEFAULT_CODE_WORDS = (
    "amber",
    "apple",
    "arrow",
    "atlas",
    "bamboo",
    "beacon",
    "birch",
    "breeze",
    "cedar",
    "cinder",
    "cobalt",
    "comet",
    "coral",
    "crystal",
    "dawn",
    "delta",
    "ember",
    "falcon",
    "forest",
    "frost",
    "garden",
    "glimmer",
    "harbor",
    "hazel",
    "horizon",
    "ivy",
    "juniper",
    "lantern",
    "lilac",
    "meadow",
    "mercury",
    "meteor",
    "mist",
    "moon",
    "oak",
    "onyx",
    "orchid",
    "phoenix",
    "pine",
    "planet",
    "prairie",
    "quartz",
    "raven",
    "reef",
    "river",
    "saffron",
    "sage",
    "shadow",
    "signal",
    "silver",
    "solstice",
    "spruce",
    "star",
    "stone",
    "sunrise",
    "thunder",
    "timber",
    "topaz",
    "valley",
    "violet",
    "wave",
    "willow",
    "winter",
)


class CodeGenerator:
    def __init__(self, word_pool: tuple[str, ...] = DEFAULT_CODE_WORDS) -> None:
        self._word_pool = word_pool
        self._rng = secrets.SystemRandom()

    def generate(self, word_count: int) -> ScrambifyCode:
        if word_count <= 0:
            raise ValueError("word count must be positive")
        if word_count > len(self._word_pool):
            raise ValueError("word count exceeds the available scrambify code word pool")
        words = tuple(self._rng.sample(self._word_pool, k=word_count))
        nameplate = self._rng.randrange(100, 1000)
        return ScrambifyCode(nameplate=nameplate, words=words)