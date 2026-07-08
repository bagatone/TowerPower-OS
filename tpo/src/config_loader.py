from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("config/settings.yaml")


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        example = Path("config/settings.example.yaml")
        raise FileNotFoundError(
            f"Configurazione non trovata: {config_path}. "
            f"Copia {example} in {config_path} e compila i valori."
        )

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    data.setdefault("dry_run", True)
    return data
