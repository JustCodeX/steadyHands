"""The one place that imports the Cactus runtime."""
from __future__ import annotations

import os


def load_cactus():
    """Import `cactus` with its network features switched off.

    By default the runtime sends telemetry and asks the Hugging Face hub for a
    config file on every transcription. Neither is acceptable here: during
    play nothing leaves the board (criteria C2 and C4). Both switches must be
    set before the import, so every use of the runtime goes through here."""
    os.environ["CACTUS_TELEMETRY"] = "0"
    os.environ["HF_HUB_OFFLINE"] = "1"
    import cactus

    return cactus
