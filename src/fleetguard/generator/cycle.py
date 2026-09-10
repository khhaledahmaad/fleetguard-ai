from __future__ import annotations

from dataclasses import dataclass

from fleetguard.contracts import OperatingState


@dataclass(frozen=True)
class OperatingCycle:
    initial_stationary_minutes: int = 10
    moving_minutes: int = 35
    braking_minutes: int = 10
    recovery_stationary_minutes: int = 5

    def __post_init__(self) -> None:
        durations = (
            self.initial_stationary_minutes,
            self.moving_minutes,
            self.braking_minutes,
            self.recovery_stationary_minutes,
        )

        if any(duration < 1 for duration in durations):
            raise ValueError("all operating-cycle durations must be positive")

    @property
    def total_minutes(self) -> int:
        return (
            self.initial_stationary_minutes
            + self.moving_minutes
            + self.braking_minutes
            + self.recovery_stationary_minutes
        )

    def state_at(self, minute_index: int) -> tuple[OperatingState, float]:
        if minute_index < 0:
            raise ValueError("minute_index cannot be negative")

        phase = minute_index % self.total_minutes

        if phase < self.initial_stationary_minutes:
            return OperatingState.STATIONARY, 0.0

        phase -= self.initial_stationary_minutes

        if phase < self.moving_minutes:
            progress = phase / max(self.moving_minutes - 1, 1)
            return OperatingState.MOVING, progress

        phase -= self.moving_minutes

        if phase < self.braking_minutes:
            progress = phase / max(self.braking_minutes - 1, 1)
            return OperatingState.BRAKING, progress

        return OperatingState.STATIONARY, 1.0


DEFAULT_OPERATING_CYCLE = OperatingCycle()
