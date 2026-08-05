"""medprov: executable provenance operators for medication exposure."""

from __future__ import annotations

__version__ = "0.1.0"

CORE_DIMENSIONS = (
    "source_layer",
    "identity_rule",
    "time_origin_window",
    "event_semantics_map",
    "required_metadata",
)

CLASSIFICATION_STATES = (
    "exposed",
    "unexposed",
    "unresolved",
    "unmeasurable",
)
