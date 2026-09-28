"""Interface stub for the V-JEPA verification stage (proprietary, not included).

The LIDAR detector in this repository raises OBSERVE and WARN events from geometry
alone. Confirming a fall (ALERT, CRITICAL) is the job of a separate video
verification stage built on V-JEPA. That stage is proprietary and is not part of this
public repository: no model, weights, configuration or decision logic ships here.

This module keeps only the typed contract, so code and documentation can name the
boundary without depending on the implementation:

  * `FusionRequest` - what the detector hands to the verification stage,
  * `FusionResult`  - what the verification stage hands back.

Nothing in this repository imports this module at runtime. `FallEvent.vjepa_confidence`
is published as NaN by the detector because no verification stage runs here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FusionRequest:
    """A LIDAR event submitted for verification."""

    track_id: int
    event_stamp_s: float
    lidar_confidence: float


@dataclass(frozen=True)
class FusionResult:
    """The verification stage's answer for one request."""

    track_id: int
    event_stamp_s: float
    vjepa_confidence: float   # 0.0 - 1.0
