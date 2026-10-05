"""Bounded recovery observations, with a separate advisory Home Assistant store.

``LearningSampler`` consumes plain observations and never owns an actuator.
Samples describe confirmed valve readiness and circulation, which is empirical
conditioning evidence, not proof of heat delivery or a measurement of COP.
Only completed episode statistics are persisted; a restart cannot resume an
observation across an unobserved interval or alter the Plant's safety state.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Final, Literal

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .core.model import LearningMode, Mode
from .core.thermal import RecoveryEpisode, RecoveryEstimate, ThermalModel, estimate, record_episode

_LOGGER = logging.getLogger(__name__)
SAMPLE_INTERVAL: Final = 300.0
STALL_INTERVAL: Final = 7200.0
MAX_EPISODE_DURATION: Final = 21600.0
LEARNING_STORE_VERSION: Final = 1
LEARNING_SAVE_DELAY: Final = 60.0
_MAX_STORED_EPISODES: Final = 128


@dataclass(frozen=True, slots=True)
class LearningSample:
    """One zone's current, already aggregated inputs and confirmed circulation.

    ``fingerprint`` identifies topology, resolved sensors, and control settings.
    ``permitted`` excludes windows, guards, frost demand, and manual interruptions.
    Temperature freshness is checked again here and distinct sensor reports, not
    repeated runtime evaluations, establish that a recovery was observed.
    """

    zone: str
    mode: Mode
    learning: LearningMode
    fingerprint: str
    temperature: float | None
    temperature_at: float | None
    target: float | None
    preset: str
    circulating: bool
    live: bool
    permitted: bool = True
    reason: str | None = None
    outdoor_temperature: float | None = None
    resolution: float = 0.1
    temperature_max_age: float = 900.0


@dataclass(slots=True)
class _ActiveEpisode:
    mode: Mode
    target: float
    preset: str
    started_at: float
    start_temperature: float
    deficit: float
    outdoor_temperature: float | None
    predicted_seconds: float | None
    last_report_at: float
    last_temperature: float
    progress_at: float
    progress_temperature: float
    reports: int = 1


@dataclass(slots=True)
class _ZoneLearning:
    fingerprint: str
    models: dict[Mode, ThermalModel] = field(default_factory=dict)
    active: _ActiveEpisode | None = None
    last_sample: LearningSample | None = None
    last_reason: str = "awaiting_circulation"


class LearningSampler:
    """Sample on a fixed cadence; censor interruptions on every input update."""

    def __init__(self) -> None:
        self.zones: dict[str, _ZoneLearning] = {}
        self.next_sample_at: float | None = None
        self._last_update_at: float | None = None
        self.revision = 0

    def update(self, samples: Mapping[str, LearningSample], now: float) -> None:
        """Observe an evaluation without counting duplicate events as samples."""
        if not isfinite(now):
            return
        clock_gap = self._last_update_at is not None and (
            now < self._last_update_at or now - self._last_update_at > SAMPLE_INTERVAL * 2
        )
        if clock_gap:
            for zone in self.zones.values():
                self._finish(zone, now, "censored", "observation_gap")
            self.next_sample_at = now
        self._last_update_at = now
        self.synchronize({slug: sample.fingerprint for slug, sample in samples.items()})
        interrupted: set[str] = set()
        for slug, sample in samples.items():
            zone = self.zones[slug]
            previous = zone.last_sample
            zone.last_sample = sample
            reason = self._invalid(sample, now)
            active = zone.active
            if active is not None and (
                active.mode != sample.mode
                or active.target != sample.target
                or active.preset != sample.preset
            ):
                reason = "thermostat_changed"
            if reason is not None:
                self._finish(zone, now, "censored", reason)
                zone.last_reason = reason
                interrupted.add(slug)
            elif active is not None and not sample.circulating:
                # A target arrival can stop its pump before this evaluation runs.
                # All guard and owner changes above still take precedence.
                self._observe(zone, sample, now)
                self._finish(zone, now, "censored", "circulation_stopped")
            elif (
                active is None
                and sample.circulating
                and (previous is None or not previous.circulating)
            ):
                # Capture the observed start exactly, including any subsequent
                # autonomous source delay. Later numeric samples keep cadence.
                self._start(zone, sample, now)
        due = self.next_sample_at is None or now >= self.next_sample_at
        if due:
            self.next_sample_at = now + SAMPLE_INTERVAL
            for slug, sample in samples.items():
                zone = self.zones[slug]
                if slug in interrupted or not sample.circulating:
                    continue
                if zone.active is None:
                    self._start(zone, sample, now)
                else:
                    self._observe(zone, sample, now)
        if not any(
            sample.live and sample.learning != LearningMode.OFF for sample in samples.values()
        ):
            self.next_sample_at = None

    def synchronize(self, fingerprints: Mapping[str, str]) -> None:
        """Invalidate changed configuration before any restored estimate is read."""
        for slug in self.zones.keys() - fingerprints.keys():
            del self.zones[slug]
            self.revision += 1
        for slug, fingerprint in fingerprints.items():
            zone = self.zones.get(slug)
            if zone is None or zone.fingerprint != fingerprint:
                self.zones[slug] = _ZoneLearning(fingerprint)
                self.revision += 1

    @staticmethod
    def _invalid(sample: LearningSample, now: float) -> str | None:
        if sample.learning == LearningMode.OFF:
            return "disabled"
        if not sample.live:
            return "dry_run"
        if not sample.permitted:
            return sample.reason or "blocked"
        if sample.mode not in (Mode.HEAT, Mode.COOL):
            return "mode_off"
        if sample.target is None or not isfinite(sample.target):
            return "target_unavailable"
        if (
            sample.temperature is None
            or not isfinite(sample.temperature)
            or sample.temperature_at is None
            or not isfinite(sample.temperature_at)
            or not isfinite(sample.temperature_max_age)
            or sample.temperature_max_age <= 0
            or sample.temperature_at > now
            or now >= sample.temperature_at + sample.temperature_max_age
        ):
            return "temperature_unavailable"
        if not isfinite(sample.resolution) or sample.resolution <= 0:
            return "temperature_resolution_unavailable"
        return None

    def _start(self, zone: _ZoneLearning, sample: LearningSample, now: float) -> None:
        assert sample.target is not None
        assert sample.temperature is not None
        assert sample.temperature_at is not None
        deficit = _deficit(sample.mode, sample.target, sample.temperature)
        if deficit <= sample.resolution:
            zone.last_reason = "no_actionable_deficit"
            return
        prediction = estimate(
            zone.models.get(sample.mode, ThermalModel()),
            sample.mode,
            deficit,
            now,
            outdoor_temperature=sample.outdoor_temperature,
        )
        zone.active = _ActiveEpisode(
            sample.mode,
            sample.target,
            sample.preset,
            now,
            sample.temperature,
            deficit,
            _optional_finite(sample.outdoor_temperature),
            prediction.seconds,
            sample.temperature_at,
            sample.temperature,
            now,
            sample.temperature,
        )
        zone.last_reason = "observing"

    def _observe(self, zone: _ZoneLearning, sample: LearningSample, now: float) -> None:
        active = zone.active
        assert active is not None
        assert sample.temperature is not None
        assert sample.temperature_at is not None
        # A report from before the episode or a duplicate report proves nothing.
        if sample.temperature_at > max(active.last_report_at, active.started_at):
            active.last_report_at = sample.temperature_at
            active.last_temperature = sample.temperature
            active.reports += 1
            movement = _deficit(active.mode, sample.temperature, active.progress_temperature)
            if movement > sample.resolution:
                active.progress_temperature = sample.temperature
                active.progress_at = now
            total_movement = _deficit(active.mode, sample.temperature, active.start_temperature)
            if (
                active.reports >= 2
                and total_movement > sample.resolution
                and _deficit(active.mode, active.target, sample.temperature) <= 0
            ):
                self._finish(zone, now, "reached", "target_reached")
                return
        # Fresh reports that show no response are real missed recoveries, even
        # when this Plant only controls valves and circulation. They lower trust.
        if active.reports >= 2 and now - active.progress_at >= STALL_INTERVAL:
            self._finish(zone, now, "failed", "no_temperature_progress")
        elif now - active.started_at >= MAX_EPISODE_DURATION:
            self._finish(
                zone,
                now,
                "failed" if active.reports >= 2 else "censored",
                "recovery_timeout" if active.reports >= 2 else "insufficient_sensor_reports",
            )

    def _finish(
        self,
        zone: _ZoneLearning,
        now: float,
        outcome: Literal["reached", "failed", "censored"],
        reason: str,
    ) -> None:
        active = zone.active
        if active is None:
            return
        zone.active = None
        zone.last_reason = reason
        if now <= active.started_at:
            return
        episode = RecoveryEpisode(
            mode=active.mode,
            started_at=active.started_at,
            ended_at=now,
            deficit=active.deficit,
            outcome=outcome,
            outdoor_temperature=active.outdoor_temperature,
            predicted_seconds=active.predicted_seconds,
            reason=reason,
        )
        zone.models[active.mode] = record_episode(
            zone.models.get(active.mode, ThermalModel()), episode, now
        )
        self.revision += 1

    def estimate(
        self,
        zone: str,
        mode: Mode,
        deficit: float,
        now: float,
        outdoor_temperature: float | None = None,
    ) -> RecoveryEstimate:
        """Return an advisory estimate with no change to the observation history."""
        state = self.zones.get(zone)
        model = ThermalModel() if state is None else state.models.get(mode, ThermalModel())
        return estimate(model, mode, deficit, now, outdoor_temperature=outdoor_temperature)

    def reset(self, zone: str) -> None:
        """Forget a zone's models and any unfinished observation."""
        state = self.zones.get(zone)
        if state is not None:
            state.models.clear()
            state.active = None
            state.last_reason = "reset"
            self.revision += 1

    def stop(self, now: float) -> None:
        """Censor open observations at the command-free lifecycle boundary."""
        for zone in self.zones.values():
            self._finish(zone, now, "censored", "stopped")
        self.next_sample_at = None

    def diagnostics(self, now: float) -> dict[str, Any]:
        """Expose evidence and bounded statistics, without claiming heat delivery."""
        result: dict[str, Any] = {}
        for slug, zone in self.zones.items():
            sample = zone.last_sample
            active = zone.active
            deficit = (
                active.deficit
                if active is not None
                else _deficit(sample.mode, sample.target, sample.temperature)
                if sample is not None
                and sample.target is not None
                and sample.temperature is not None
                else 1.0
            )
            result[slug] = {
                "evidence": "inferred_circulation",
                "heat_delivery_measured": False,
                "reason": zone.last_reason,
                "active": None
                if active is None
                else {
                    "mode": active.mode.value,
                    "started_at": active.started_at,
                    "reports": active.reports,
                    "predicted_seconds": active.predicted_seconds,
                },
                "models": {
                    mode.value: {
                        "episodes": len(zone.models.get(mode, ThermalModel()).episodes),
                        "estimate": asdict(
                            self.estimate(
                                slug,
                                mode,
                                max(0.0, deficit),
                                now,
                                None if sample is None else sample.outdoor_temperature,
                            )
                        ),
                    }
                    for mode in (Mode.HEAT, Mode.COOL)
                },
            }
        return {"sample_interval": SAMPLE_INTERVAL, "zones": result}

    def to_dict(self) -> dict[str, Any]:
        """Persist only bounded completed episodes and configuration identities."""
        return {
            "zones": {
                slug: {
                    "fingerprint": zone.fingerprint,
                    "models": {
                        mode.value: {"episodes": [asdict(episode) for episode in model.episodes]}
                        for mode, model in zone.models.items()
                    },
                }
                for slug, zone in self.zones.items()
            }
        }

    def load(self, data: object, now: float) -> None:
        """Read a separate advisory store, isolating corrupt zones from each other."""
        self.zones.clear()
        self.next_sample_at = None
        self._last_update_at = None
        if not isinstance(data, dict) or not isinstance(data.get("zones"), dict):
            return
        for slug, raw in data["zones"].items():
            try:
                if not isinstance(slug, str) or not isinstance(raw, dict):
                    raise ValueError("invalid zone record")
                fingerprint = raw["fingerprint"]
                if not isinstance(fingerprint, str) or not isinstance(raw["models"], dict):
                    raise ValueError("invalid model identity")
                zone = _ZoneLearning(fingerprint, last_reason="restored_without_active_episode")
                for mode_name, raw_model in raw["models"].items():
                    mode = Mode(mode_name)
                    if mode == Mode.OFF or not isinstance(raw_model, dict):
                        raise ValueError("invalid model mode")
                    episodes = raw_model["episodes"]
                    if not isinstance(episodes, list):
                        raise ValueError("invalid episode list")
                    model = ThermalModel()
                    ordered = sorted(
                        (
                            _load_episode(raw_episode, mode)
                            for raw_episode in episodes[-_MAX_STORED_EPISODES:]
                        ),
                        key=lambda episode: (episode.started_at, episode.ended_at),
                    )
                    for episode in ordered:
                        model = record_episode(model, episode, now)
                    zone.models[mode] = model
                self.zones[slug] = zone
            except KeyError, TypeError, ValueError, OverflowError:
                _LOGGER.warning("Discarding invalid thermal learning model for zone %s", slug)


class LearningCoordinator:
    """Persist advisory learning independently from hydraulic safety state."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.sampler = LearningSampler()
        self.store: Store[dict[str, Any]] = Store(hass, LEARNING_STORE_VERSION, store_key(entry_id))
        self._queued_revision = self.sampler.revision
        self._stopped = False
        self._flushed = False

    @property
    def next_sample_at(self) -> float | None:
        """The fixed observation cadence's next deadline, if enabled."""
        return self.sampler.next_sample_at

    async def async_load(self) -> None:
        """Restore advisory history without touching the runtime's safety store."""
        try:
            self.sampler.load(await self.store.async_load(), dt_util.utcnow().timestamp())
        except Exception as error:
            _LOGGER.warning("Thermal learning history could not be read: %s", error)
            self.sampler = LearningSampler()
        self._queued_revision = self.sampler.revision

    def update(self, samples: Mapping[str, LearningSample], now: float) -> None:
        """Accept one runtime snapshot and queue only changed episode history."""
        if self._stopped:
            return
        self.sampler.update(samples, now)
        self._save_changed()

    def estimate(
        self,
        zone: str,
        mode: Mode,
        deficit: float,
        now: float,
        outdoor_temperature: float | None = None,
    ) -> RecoveryEstimate:
        """Read one zone's current empirical prediction."""
        return self.sampler.estimate(zone, mode, deficit, now, outdoor_temperature)

    def reset(self, zone: str) -> None:
        """Reset only the selected zone's advisory history."""
        self.sampler.reset(zone)
        self._save_changed()

    def synchronize(self, fingerprints: Mapping[str, str]) -> None:
        """Validate restored model identities before the runtime requests estimates."""
        if not self._stopped:
            self.sampler.synchronize(fingerprints)
            self._save_changed()

    def diagnostics(self, now: float) -> dict[str, Any]:
        """Return the bounded advisory evidence and model diagnostics."""
        return self.sampler.diagnostics(now)

    def _save_changed(self) -> None:
        if self._queued_revision != self.sampler.revision:
            self._queued_revision = self.sampler.revision
            data = self.sampler.to_dict()
            self.store.async_delay_save(lambda: data, LEARNING_SAVE_DELAY)

    def stop(self, now: float) -> None:
        """Prevent further updates and censor unfinished observations synchronously."""
        if self._stopped:
            return
        self._stopped = True
        self.sampler.stop(now)
        # Store listens for Home Assistant's final-write event even when stop
        # is already dispatching, so lifecycle censorship cannot be lost.
        data = self.sampler.to_dict()
        self.store.async_delay_save(lambda: data)

    async def async_stop(self, now: float | None = None) -> None:
        """Censor unfinished observations and flush the isolated learning store."""
        self.stop(dt_util.utcnow().timestamp() if now is None else now)
        if self._flushed:
            return
        await self.store.async_save(self.sampler.to_dict())
        self._flushed = True


def store_key(entry_id: str) -> str:
    """Keep learning data outside the authoritative hydraulic runtime store."""
    return f"{DOMAIN}.{entry_id}.learning"


def _deficit(mode: Mode, target: float, temperature: float) -> float:
    return temperature - target if mode == Mode.COOL else target - temperature


def _optional_finite(value: float | None) -> float | None:
    return value if value is not None and isfinite(value) else None


def _number(raw: object) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not isfinite(raw):
        raise ValueError("expected a finite number")
    return float(raw)


def _load_episode(raw: object, mode: Mode) -> RecoveryEpisode:
    if not isinstance(raw, dict) or raw.get("mode") != mode.value:
        raise ValueError("invalid episode mode")
    outcome = raw["outcome"]
    if outcome not in ("reached", "failed", "censored"):
        raise ValueError("invalid recovery outcome")
    started = _number(raw["started_at"])
    ended = _number(raw["ended_at"])
    deficit = _number(raw["deficit"])
    if ended <= started or deficit <= 0:
        raise ValueError("invalid recovery interval or deficit")
    reason = raw.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise ValueError("invalid recovery reason")
    optional = {
        name: None if raw.get(name) is None else _number(raw[name])
        for name in (
            "outdoor_temperature",
            "predicted_seconds",
            "baseline_predicted_seconds",
            "weather_predicted_seconds",
        )
    }
    if any(
        value is not None and value < 0
        for name, value in optional.items()
        if name != "outdoor_temperature"
    ):
        raise ValueError("invalid predicted duration")
    return RecoveryEpisode(
        mode=mode,
        started_at=started,
        ended_at=ended,
        deficit=deficit,
        outcome=outcome,
        reason=reason,
        **optional,
    )
