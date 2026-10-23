"""Validated historical bundle contracts shared by storage and the API."""

from __future__ import annotations

from datetime import UTC
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)

from raceos.data import DataError, SCHEMA_VERSION

Source = Literal["fastf1", "tracinginsights"]


class Record(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class SessionRecord(Record):
    id: str = Field(min_length=1)
    year: StrictInt = Field(ge=2018)
    location: str = Field(min_length=1)
    name: str = Field(min_length=1)
    scheduled_start_utc: AwareDatetime


class DriverRecord(Record):
    number: StrictInt = Field(gt=0)
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    team: str | None = None
    team_color: str | None = None


class LapRecord(Record):
    source: Source | None = None
    driver_number: StrictInt = Field(gt=0)
    lap_number: StrictInt = Field(gt=0)
    lap_duration_s: float | None = Field(default=None, gt=0)
    lap_start_utc: AwareDatetime | None = None
    lap_end_utc: AwareDatetime | None = None


class TelemetryRecord(Record):
    source: Source
    driver_number: StrictInt = Field(gt=0)
    timestamp_utc: AwareDatetime
    speed_kmh: float | None = None
    throttle_pct: float | None = None
    brake_pressed: StrictBool | None = None
    gear: float | None = None
    rpm: float | None = None
    drs_code: float | None = None


class PositionRecord(Record):
    source: Source
    driver_number: StrictInt = Field(gt=0)
    timestamp_utc: AwareDatetime
    x: float | None = None
    y: float | None = None
    z: float | None = None
    status: str | None = None


class Bundle(Record):
    schema_version: StrictInt
    source: Literal["fastf1"]
    session: SessionRecord
    driver: DriverRecord
    drivers: list[DriverRecord] = Field(min_length=1)
    laps: list[LapRecord] = Field(min_length=1)
    telemetry: list[TelemetryRecord] = Field(min_length=1)
    # None means an older bundle without position data. Keep existing positions.
    positions: list[PositionRecord] | None = None

    @model_validator(mode="after")
    def check_relationships(self):
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported normalized bundle schema {self.schema_version}."
            )
        if self.session.scheduled_start_utc.astimezone(UTC).year != self.session.year:
            raise ValueError("Session year and UTC start year do not match.")
        numbers = [driver.number for driver in self.drivers]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Driver numbers must be unique within a provider session.")
        selected = next(
            (driver for driver in self.drivers if driver.number == self.driver.number),
            None,
        )
        if selected is None or selected.code != self.driver.code:
            raise ValueError(
                "Selected driver must match a member of the session driver list."
            )
        lap_keys = [(lap.driver_number, lap.lap_number) for lap in self.laps]
        if len(lap_keys) != len(set(lap_keys)):
            raise ValueError("Lap identities must be unique within a provider session.")
        for lap in self.laps:
            if lap.driver_number not in numbers or lap.source not in (
                None,
                self.source,
            ):
                raise ValueError("Lap identity or provider does not match the bundle.")
        for sample in self.telemetry:
            if (
                sample.driver_number != self.driver.number
                or sample.source != self.source
            ):
                raise ValueError(
                    "Telemetry must belong to the selected driver and provider."
                )
        for position in self.positions or []:
            if (
                position.driver_number != self.driver.number
                or position.source != self.source
            ):
                raise ValueError(
                    "Position records must match the selected driver and source."
                )
        for lap in self.laps:
            if (
                lap.lap_start_utc
                and lap.lap_end_utc
                and lap.lap_end_utc < lap.lap_start_utc
            ):
                raise ValueError("A lap cannot end before it starts.")
        return self


def validated_bundle(value: dict) -> Bundle:
    try:
        return Bundle.model_validate(value)
    except ValueError as error:
        raise DataError(f"Invalid session bundle: {error}") from error
