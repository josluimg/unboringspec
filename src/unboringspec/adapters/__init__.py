from __future__ import annotations

from pathlib import Path

from .base import Adapter
from .generic import GenericAdapter
from .speckit import SpecKitAdapter

# Order matters: most specific first, generic last.
ADAPTERS: list[type[Adapter]] = [SpecKitAdapter, GenericAdapter]


def get_adapter(path: Path, name: str | None = None) -> Adapter:
    if name:
        for a in ADAPTERS:
            if a.name == name:
                return a()
        raise ValueError(f"Unknown adapter '{name}'. Available: {', '.join(a.name for a in ADAPTERS)}")
    for a in ADAPTERS:
        if a.detect(path):
            return a()
    raise ValueError(f"No Markdown spec files found in {path}")


__all__ = ["ADAPTERS", "Adapter", "get_adapter"]
