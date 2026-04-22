"""Structural protocol shared by all IMU receivers.

Any receiver (OSC, BLE, future Serial) that feeds ``FusionEngine`` must
satisfy this protocol. The ``@runtime_checkable`` decorator allows
``isinstance(receiver, IMUReceiver)`` checks in verification scripts.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from scipy.spatial.transform import Rotation


@runtime_checkable
class IMUReceiver(Protocol):
    """Common pull-style interface exposed by every IMU receiver.

    Semantics:
    - ``is_connected`` is True iff a rotation sample was received within
      the last second (not merely "link layer connected"). This keeps the
      state machine's IMU_DISCONNECTED logic receiver-agnostic.
    - ``get_bone_rotation`` returns ``None`` for stale (>1s old) samples.
    """

    @property
    def is_connected(self) -> bool: ...

    @property
    def seconds_since_last_receive(self) -> float: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def get_bone_rotation(self, bone_name: str) -> Rotation | None: ...
