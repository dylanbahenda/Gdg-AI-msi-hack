"""
Event Grouper — collapses consecutive same-class detections into one event.

A real-world sound (a clap, a scream, an alarm pulse) typically spans multiple
sliding windows.  Without grouping, every window emits its own notification:
the user sees three "scream" alerts when the speaker shouted once.

This module sits between the per-window detection stream and the LLM /
notification stage.  It buffers same-class events within a tolerance gap and
emits a single weighted summary when:
  - a different-class event arrives (forces finalisation of the current group)
  - the periodic flusher detects no new same-class window for > tolerance

Aggregation rules (rationale: see the conversation that produced this file):
  - direction:  confidence-weighted CIRCULAR mean (handles 0°/360° wrap)
  - distance:   confidence-weighted arithmetic mean
  - confidence: max across windows
  - timestamp:  first window's timestamp
  - duration:   last_end − first_start  (last_end = last_window_ts + WINDOW_SIZE_S)

The granular per-window stream is *not* destroyed — it is emitted in parallel
to ``event_bus.emit_raw_event`` by the orchestrator.  The grouper only owns
the merged-notification path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, cos, degrees, radians, sin

from contracts.config import EVENT_MERGE_TOLERANCE_S, WINDOW_SIZE_S
from contracts.types import AlignedEvent, SoundClass


@dataclass
class GroupedEvent:
    """A merged event ready to be passed to the LLM and emitted as an alert."""
    sound_class: SoundClass
    timestamp: float                # start of first window
    direction_of_arrival: float     # 0–359.9°, weighted circular mean
    distance_estimation: float      # metres, weighted mean
    sed_confidence: float           # max across windows
    duration_s: float               # last_end − first_start
    window_count: int               # raw windows merged


@dataclass
class _PendingGroup:
    """Mutable accumulator for one in-progress event."""
    sound_class: SoundClass
    first_timestamp: float
    last_timestamp: float
    # Confidence-weighted accumulators
    weighted_unit_x: float = 0.0    # sum(conf_i * cos(angle_i))
    weighted_unit_y: float = 0.0    # sum(conf_i * sin(angle_i))
    weighted_distance: float = 0.0  # sum(conf_i * distance_i)
    weight_sum: float = 0.0         # sum(conf_i)
    max_confidence: float = 0.0
    window_count: int = 0
    raw_windows: list[AlignedEvent] = field(default_factory=list)

    def add(self, ev: AlignedEvent) -> None:
        weight = max(ev.sed_confidence, 1e-6)  # avoid zero-weight degenerate case
        theta = radians(ev.doa_direction_of_arrival)
        self.weighted_unit_x += weight * cos(theta)
        self.weighted_unit_y += weight * sin(theta)
        self.weighted_distance += weight * ev.doa_distance_estimation
        self.weight_sum += weight
        self.max_confidence = max(self.max_confidence, ev.sed_confidence)
        self.last_timestamp = ev.timestamp
        self.window_count += 1
        self.raw_windows.append(ev)

    def finalize(self) -> GroupedEvent:
        # Circular mean of direction (handles wrap at 0°/360°).
        mean_angle_rad = atan2(self.weighted_unit_y, self.weighted_unit_x)
        mean_angle_deg = degrees(mean_angle_rad) % 360
        # Distance: simple weighted arithmetic mean.
        mean_distance = self.weighted_distance / self.weight_sum
        last_end = self.last_timestamp + WINDOW_SIZE_S
        return GroupedEvent(
            sound_class=self.sound_class,
            timestamp=self.first_timestamp,
            direction_of_arrival=round(mean_angle_deg, 1),
            distance_estimation=round(mean_distance, 2),
            sed_confidence=round(self.max_confidence, 4),
            duration_s=round(last_end - self.first_timestamp, 2),
            window_count=self.window_count,
        )


class EventGrouper:
    """
    Holds at most one pending group per sound class.

    Usage:
        grouper = EventGrouper()
        for ev in detected_windows:
            for finalized in grouper.add(ev):
                # forward `finalized` to LLM + AlertNotification
                ...
        # Periodically:
        for finalized in grouper.flush_stale(now=time.time()):
            ...
    """

    def __init__(
        self,
        merge_tolerance_s: float = EVENT_MERGE_TOLERANCE_S,
    ) -> None:
        self.merge_tolerance_s = merge_tolerance_s
        self._pending: dict[SoundClass, _PendingGroup] = {}

    def add(self, ev: AlignedEvent) -> list[GroupedEvent]:
        """
        Accumulate `ev` and return any groups that finalised because of it.

        A group finalises when a same-class event arrives after the tolerance
        gap (the older group is flushed, then `ev` starts a fresh one).
        Different-class events do NOT pre-empt other classes' pending groups
        — they accumulate independently.
        """
        finalized: list[GroupedEvent] = []
        cls = ev.sound_class
        existing = self._pending.get(cls)

        if existing is not None and ev.timestamp - existing.last_timestamp <= self.merge_tolerance_s:
            existing.add(ev)
            return finalized

        # Either no pending group for this class, or gap exceeded → finalize old, start new.
        if existing is not None:
            finalized.append(existing.finalize())

        new_group = _PendingGroup(
            sound_class=cls,
            first_timestamp=ev.timestamp,
            last_timestamp=ev.timestamp,
        )
        new_group.add(ev)
        self._pending[cls] = new_group
        return finalized

    def flush_stale(self, now: float) -> list[GroupedEvent]:
        """
        Finalise any pending group whose last detection is older than the
        tolerance.  Call periodically so the last event of a stream emits
        even if no new detection arrives.
        """
        stale: list[GroupedEvent] = []
        cutoff = now - self.merge_tolerance_s
        for cls in list(self._pending.keys()):
            group = self._pending[cls]
            if group.last_timestamp < cutoff:
                stale.append(group.finalize())
                del self._pending[cls]
        return stale

    def flush_all(self) -> list[GroupedEvent]:
        """Force-finalise every pending group — used at shutdown."""
        out = [g.finalize() for g in self._pending.values()]
        self._pending.clear()
        return out
