"""The source compressor's starts and runs, for its diagnostic sensors.

Every evaluation tells the history whether the compressor runs, read from the
source's ``compressor_sensor``, a numeric sensor that reads above zero while it
runs, such as its frequency. The history keeps each start of the last hour and
each run that ended within the last day, and persists with the Plant's store.
An unknown reading changes nothing, so a short loss of the sensor neither ends
nor starts a run.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

HOUR: Final = 3600.0
DAY: Final = 86400.0


@dataclass(slots=True)
class CompressorHistory:
    running_since: float | None = None
    starts: list[float] = field(default_factory=list)
    # Each run that ended within the last day, as (ended, seconds).
    runs: list[tuple[float, float]] = field(default_factory=list)

    def observe(self, now: float, running: bool | None) -> None:
        """Take whether the compressor runs now; None while that is unknown."""
        if running is True and self.running_since is None:
            self.running_since = now
            self.starts.append(now)
        elif running is False and self.running_since is not None:
            self.runs.append((now, now - self.running_since))
            self.running_since = None
        self.starts = [start for start in self.starts if start > now - HOUR]
        self.runs = [run for run in self.runs if run[0] > now - DAY]

    def starts_within_hour(self, now: float) -> int:
        return sum(1 for start in self.starts if start > now - HOUR)

    def mean_run(self, now: float) -> float | None:
        """The mean length of the runs that ended within the last day, in seconds."""
        runs = [seconds for ended, seconds in self.runs if ended > now - DAY]
        return sum(runs) / len(runs) if runs else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "running_since": self.running_since,
            "starts": list(self.starts),
            "runs": [list(run) for run in self.runs],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CompressorHistory:
        since = data.get("running_since")
        return cls(
            running_since=None if since is None else float(since),
            starts=[float(start) for start in data.get("starts", ())],
            runs=[(float(ended), float(seconds)) for ended, seconds in data.get("runs", ())],
        )
