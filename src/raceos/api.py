"""Read API over the stored historical data; provider downloads stay in the CLI."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Generic, TypeVar, Literal

from fastapi import FastAPI, HTTPException, Path as ApiPath, Query, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AwareDatetime, BaseModel, Field, StrictInt

from raceos import __version__, replay
from raceos.contracts import DriverRecord, LapRecord, Source, TelemetryRecord
from raceos.data import DataError
from raceos.storage import DB_SCHEMA_VERSION, DEFAULT_DB, NotFound, Store
from raceos.providers.tracinginsights import TracingInsights
from raceos.remote_cache import RemoteUnavailable
from raceos.remote_replay import RemoteReplay
from raceos.analysis import PerformanceAnalysis, LapComparison

Item = TypeVar("Item")


class Page(BaseModel, Generic[Item]):
    items: list[Item]
    total: int
    limit: int
    offset: int
    next_offset: int | None


class SourcePage(Page[Item], Generic[Item]):
    session_id: str
    source: Source


class Coverage(BaseModel):
    driver_number: int
    sample_count: int
    first_imported_at_utc: AwareDatetime
    last_imported_at_utc: AwareDatetime


class SessionSource(BaseModel):
    source: Source
    source_session_id: str
    input_schema_version: int
    telemetry_drivers: list[Coverage]


class Session(BaseModel):
    id: str
    year: int
    location: str
    name: str
    scheduled_start_utc: AwareDatetime
    default_source: Source
    sources: list[SessionSource]


class Driver(DriverRecord):
    telemetry_available: bool
    telemetry_samples: int


class Drivers(BaseModel):
    session_id: str
    source: Source
    items: list[Driver]


class Telemetry(TelemetryRecord):
    sample_index: int
    quality_flags: list[str]


class Quality(BaseModel):
    session_id: str
    source: Source
    driver_number: int
    profile: dict[str, Any]


class Health(BaseModel):
    status: str
    version: str
    database_schema_version: int
    counts: dict[str, int]
    provider: str = "tracinginsights"
    cache: dict[str, Any] | None = None


class OpenSession(BaseModel):
    year: StrictInt = Field(ge=2018, le=2100)
    round: StrictInt = Field(gt=0, le=30)
    session: Literal["Race", "Qualifying"]


DriverNumber = Annotated[int, ApiPath(gt=0)]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=5000)]


def create_app(
    db_path: Path | str | None = None,
    frontend_dir: Path | str | None = None,
    *,
    remote_provider=None,
) -> FastAPI:
    store = Store(db_path or os.environ.get("RACEOS_DB_PATH", str(DEFAULT_DB)))
    provider = remote_provider or TracingInsights(store.path.parent / "remote")
    remote = RemoteReplay(provider)
    analysis = PerformanceAnalysis(provider)
    dashboard = (
        Path(frontend_dir)
        if frontend_dir is not None
        else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    )

    @asynccontextmanager
    async def lifespan(application):
        store.initialize()
        try:
            yield
        finally:
            if remote_provider is None:
                provider.cache.close()

    application = FastAPI(
        title="RaceOS API",
        version=__version__,
        lifespan=lifespan,
        description="TracingInsights remote replay with a bounded local cache; legacy FastF1 archive API.",
    )

    application.state.remote = provider
    application.state.remote_replay = remote

    @application.exception_handler(RemoteUnavailable)
    async def remote_error(request, error):
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @application.get("/api/library", tags=["Remote data"])
    def remote_library():
        items = provider.library()
        return {"items": items, "total": len(items), "source": "tracinginsights"}

    @application.get("/api/remote/events", tags=["Remote data"])
    def remote_events(year: Annotated[int, Query(ge=2018, le=2100)]):
        return {"year": year, "items": provider.events(year)}

    @application.post("/api/remote/open", tags=["Remote data"])
    def open_session(selection: OpenSession):
        item = provider.open(
            selection.year, selection.round, selection.session, validate=remote.track
        )
        return item

    @application.get("/api/remote/cache", tags=["Remote data"])
    def cache_status():
        return provider.cache.info()

    def check_source(sid, source):
        expected = "tracinginsights" if sid.startswith("ti-") else "fastf1"
        if source is not None and source != expected:
            raise DataError("The requested source does not match this session.")

    @application.get("/", include_in_schema=False)
    def homepage():
        index = dashboard / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return HTMLResponse(
            '<h1>RaceOS dashboard needs a build</h1><p>From the frontend folder, run <code>npm ci</code> and <code>npm run build</code>, then refresh this page.</p><p><a href="/docs">API documentation</a></p>',
            status_code=503,
        )

    @application.get("/favicon.svg", include_in_schema=False)
    def favicon():
        icon = dashboard / "favicon.svg"
        if not icon.is_file():
            raise HTTPException(status_code=404, detail="Icon not found.")
        return FileResponse(icon)

    application.mount(
        "/assets",
        StaticFiles(directory=dashboard / "assets", check_dir=False),
        name="dashboard-assets",
    )

    @application.exception_handler(NotFound)
    async def not_found_handler(request, error):
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(DataError)
    async def data_error_handler(request, error):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @application.get("/api/health", response_model=Health, tags=["Health"])
    def health():
        return {
            "status": "ok",
            "version": __version__,
            "database_schema_version": DB_SCHEMA_VERSION,
            "counts": store.counts(),
            "cache": provider.cache.info(),
        }

    @application.get("/api/sessions", response_model=Page[Session], tags=["Sessions"])
    def sessions(
        year: Annotated[int | None, Query(ge=2018)] = None,
        location: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Offset = 0,
    ):
        return store.sessions(year=year, location=location, limit=limit, offset=offset)

    @application.get(
        "/api/sessions/{session_id}", response_model=Session, tags=["Sessions"]
    )
    def session(session_id: str):
        return store.session(session_id)

    @application.get(
        "/api/sessions/{session_id}/drivers", response_model=Drivers, tags=["Drivers"]
    )
    def drivers(session_id: str, source: Source | None = None):
        return store.drivers(session_id, source)

    @application.get(
        "/api/sessions/{session_id}/drivers/{driver_number}/laps",
        response_model=SourcePage[LapRecord],
        tags=["Laps"],
    )
    def laps(
        session_id: str,
        driver_number: DriverNumber,
        source: Source | None = None,
        limit: Limit = 100,
        offset: Offset = 0,
    ):
        return store.laps(
            session_id, driver_number, source=source, limit=limit, offset=offset
        )

    @application.get(
        "/api/sessions/{session_id}/drivers/{driver_number}/telemetry",
        response_model=SourcePage[Telemetry],
        tags=["Telemetry"],
    )
    def telemetry(
        session_id: str,
        driver_number: DriverNumber,
        source: Source | None = None,
        lap_number: Annotated[int | None, Query(gt=0)] = None,
        start: Annotated[
            AwareDatetime | None, Query(description="Inclusive start, with timezone.")
        ] = None,
        end: Annotated[
            AwareDatetime | None, Query(description="Exclusive end, with timezone.")
        ] = None,
        limit: Limit = 1000,
        offset: Offset = 0,
    ):
        if start is not None and end is not None and end <= start:
            raise HTTPException(status_code=422, detail="End must be later than start.")
        return store.telemetry(
            session_id,
            driver_number,
            source=source,
            lap_number=lap_number,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )

    @application.get(
        "/api/sessions/{session_id}/drivers/{driver_number}/quality",
        response_model=Quality,
        tags=["Telemetry"],
    )
    def quality(
        session_id: str,
        driver_number: DriverNumber,
        source: Source | None = None,
        lap_number: Annotated[int | None, Query(gt=0)] = None,
    ):
        check_source(session_id, source)
        if session_id.startswith("ti-"):
            return remote.quality(session_id, driver_number, lap_number or 1)
        return store.quality(session_id, driver_number, source)

    @application.get("/api/sessions/{session_id}/track", tags=["Replay"])
    def circuit_track(session_id: str, source: Source | None = None):
        check_source(session_id, source)
        return (
            remote.track(session_id)
            if session_id.startswith("ti-")
            else replay.track(store, session_id)
        )

    @application.get("/api/sessions/{session_id}/replay", tags=["Replay"])
    def replay_catalog(session_id: str, source: Source | None = None):
        check_source(session_id, source)
        return (
            remote.catalog(session_id)
            if session_id.startswith("ti-")
            else replay.catalog(store, session_id)
        )

    @application.get(
        "/api/sessions/{session_id}/replay/frame",
        response_model=replay.ReplayFrame,
        tags=["Replay"],
    )
    def replay_frame(
        session_id: str,
        response: Response,
        at: Annotated[
            AwareDatetime, Query(description="Recorded event time, with timezone.")
        ],
        driver_number: Annotated[int | None, Query(gt=0)] = None,
        source: Source | None = None,
    ):
        response.headers["Cache-Control"] = "no-store"
        check_source(session_id, source)
        return (
            remote.snapshot(session_id, at, driver_number)
            if session_id.startswith("ti-")
            else replay.snapshot(store, session_id, at, driver_number)
        )

    @application.get("/api/sessions/{session_id}/analysis/laps", tags=["Performance"])
    def completed_analysis_laps(
        session_id: str,
        response: Response,
        at: Annotated[
            AwareDatetime,
            Query(description="Replay clock; only completed laps are returned."),
        ],
    ):
        response.headers["Cache-Control"] = "no-store"
        return analysis.choices(session_id, at)

    @application.get(
        "/api/sessions/{session_id}/analysis/compare",
        response_model=LapComparison,
        tags=["Performance"],
    )
    def compare_laps(
        session_id: str,
        response: Response,
        at: Annotated[
            AwareDatetime,
            Query(description="Replay clock; both laps must already be complete."),
        ],
        driver_a: Annotated[int, Query(gt=0)],
        lap_a: Annotated[int, Query(gt=0)],
        driver_b: Annotated[int, Query(gt=0)],
        lap_b: Annotated[int, Query(gt=0)],
    ):
        response.headers["Cache-Control"] = "no-store"
        return analysis.compare(session_id, at, driver_a, lap_a, driver_b, lap_b)

    return application


app = create_app()
