"""Template-method base for IMU receivers.

Every receiver (OSC / BLE / Serial / future transports) shares the same
lifecycle shape: a background thread polls or awaits the transport,
decodes frames into per-bone rotations, and exposes freshness-aware
reads. ``BaseIMUReceiver`` owns that shape so each concrete receiver
only has to describe *what* runs in the thread and *what* needs
preparing or tearing down around it.

The ``IMUReceiver`` Protocol in ``receiver_protocol.py`` is the public
contract. This base class is an implementation detail — consumers
still type against the Protocol.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field

from scipy.spatial.transform import Rotation

logger = logging.getLogger(__name__)


DEFAULT_FRESHNESS_WINDOW_SEC = 1.0


@dataclass
class BoneData:
    """Latest rotation sample for a single bone."""

    rotation: Rotation = field(default_factory=Rotation.identity)
    timestamp: float = 0.0


class BaseIMUReceiver(ABC):
    """Common lifecycle for IMU receivers.

    Subclasses implement the transport-specific hooks (``_run_loop``
    always; ``_prepare_start`` / ``_on_stop_requested`` when they need
    them). The rest — idempotent start/stop, thread join with timeout,
    freshness-aware reads — is handled here.

    The freshness window (default 1 second) doubles as the threshold for
    ``is_connected``: if no sample arrives within the window, the
    receiver is considered disconnected from the fusion engine's point
    of view, even if the physical link is up.
    """

    def __init__(
        self, freshness_window_sec: float = DEFAULT_FRESHNESS_WINDOW_SEC
    ) -> None:
        self.freshness_window_sec = freshness_window_sec
        self.bones: dict[str, BoneData] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_receive_time: float = 0.0

    # ------------------------------------------------------------------
    # Public read surface (satisfies IMUReceiver Protocol)
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """True iff a sample arrived within the freshness window."""
        if self._last_receive_time == 0.0:
            return False
        return (
            time.monotonic() - self._last_receive_time
        ) < self.freshness_window_sec

    @property
    def seconds_since_last_receive(self) -> float:
        if self._last_receive_time == 0.0:
            return float("inf")
        return time.monotonic() - self._last_receive_time

    def get_bone_rotation(self, bone_name: str) -> Rotation | None:
        """Return the freshest rotation for ``bone_name``, or ``None``.

        Returns ``None`` when the bone is unknown, when no sample has
        arrived yet (timestamp 0.0), or when the last sample is older
        than the freshness window.
        """
        bone = self.bones.get(bone_name)
        if bone is None or bone.timestamp == 0.0:
            return None
        if (time.monotonic() - bone.timestamp) > self.freshness_window_sec:
            return None
        return bone.rotation

    # ------------------------------------------------------------------
    # Lifecycle (final — subclasses don't override these)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Idempotently spawn the background reader thread.

        ``_prepare_start`` runs **before** ``_running`` is set and
        before the thread is spawned, so any exception it raises
        leaves the receiver in a clean stopped state. Use this hook
        for one-shot setup that can fail fast (e.g. opening a listen
        socket).
        """
        if self._running:
            return
        self._prepare_start()
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=self._thread_name(),
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal shutdown, run the subclass teardown, and join."""
        self._running = False
        self._on_stop_requested()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            if thread.is_alive():
                logger.warning(
                    "%s thread did not exit within 2s",
                    type(self).__name__,
                )
        self._thread = None

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------

    @abstractmethod
    def _thread_name(self) -> str:
        """Name for the background thread — aids debugging."""

    @abstractmethod
    def _run_loop(self) -> None:
        """Thread entry point. Must honor ``self._running``."""

    def _prepare_start(self) -> None:
        """One-shot setup before the thread is spawned.

        Runs synchronously on the caller of ``start()``. Exceptions
        raised here abort ``start()`` without setting ``_running``,
        preserving the "fail fast and stay stopped" invariant that
        callers rely on (e.g. ``OSError`` on a port in use).
        """

    def _on_stop_requested(self) -> None:
        """Nudge the running thread toward exit before we join it.

        For blocking-IO transports (serial / sockets) this typically
        closes the handle so a read wakes up. For asyncio-based
        transports (BLE) it schedules a cancellation on the loop.
        """

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def warn_on_unknown_bones(bone_names: Iterable[str], transport: str) -> None:
        """Warn when a bone mapping points at names FusionEngine won't read.

        Catches typos like ``"hips"`` / ``"LeftFeet"`` that would
        otherwise silently leave the target bone empty forever.
        ``transport`` is a short label (``"BLE"`` / ``"Serial"``) used
        only in the warning message.
        """
        # Lazy import: the receivers live in infrastructure but the list
        # of known bones is a domain concept — keeping the import inside
        # the method avoids forcing every BaseIMUReceiver import to pull
        # in the full tracking stack.
        from osc_tracking.domain.bones import JOINT_NAMES

        known = set(JOINT_NAMES)
        unknown = sorted({bone for bone in bone_names if bone not in known})
        if unknown:
            logger.warning(
                "%s bone mapping contains unknown bone name(s) %s; "
                "these entries will receive data but FusionEngine "
                "will never read them. Valid names: %s",
                transport,
                unknown,
                sorted(known),
            )
