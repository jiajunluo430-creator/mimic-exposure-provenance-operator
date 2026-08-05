"""Built-in medprov adapters."""

from __future__ import annotations

from .base import AdapterError, BaseAdapter, DataUnavailableError, UnmeasurableError
from .eicu import EicuAdapter
from .mimic_fhir import MimicFHIRAdapter
from .mimic_native import MimicNativeAdapter
from .omop import OmopAdapter
from .synthetic import SyntheticAdapter

ADAPTERS: dict[str, type[BaseAdapter]] = {
    "mimic_native": MimicNativeAdapter,
    "mimic_fhir": MimicFHIRAdapter,
    "omop": OmopAdapter,
    "eicu": EicuAdapter,
    "synthetic": SyntheticAdapter,
}


def get_adapter(name: str) -> BaseAdapter:
    normalized = name.strip().lower()
    if normalized not in ADAPTERS:
        raise KeyError(f"Unknown adapter '{name}'. Available: {', '.join(sorted(ADAPTERS))}")
    return ADAPTERS[normalized]()


__all__ = [
    "ADAPTERS",
    "AdapterError",
    "BaseAdapter",
    "DataUnavailableError",
    "UnmeasurableError",
    "get_adapter",
]
