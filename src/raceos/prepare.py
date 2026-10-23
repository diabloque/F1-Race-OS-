"""Prepare replay from the existing FastF1 cache, without downloading new data."""

from raceos.data import DataError, session_directory, write_json
from raceos.providers import fastf1
from raceos.storage import Store
from raceos.track import build_track


def prepare_replay(data_dir, database, *, year=None, location=None, session_name=None):
    store = Store(database)
    store.initialize()
    sessions = store.sessions(year=year, location=location, limit=100)["items"]
    if session_name:
        sessions = [
            item
            for item in sessions
            if item["name"].casefold() == session_name.casefold()
        ]
    if not sessions:
        raise DataError("Import a matching historical FastF1 session first.")
    for item in sessions:
        print(
            f"Preparing {item['year']} {item['location']} {item['name']} from local cache",
            flush=True,
        )
        session = fastf1.load_session(
            data_dir / "cache" / "fastf1",
            item["year"],
            item["location"],
            item["name"],
            offline=True,
        )
        track_saved = False
        for driver in session.results["DriverNumber"]:
            car = session.car_data.get(str(driver))
            pos = session.pos_data.get(str(driver))
            if car is None or pos is None or car.empty or pos.empty:
                print(
                    f"  Driver #{driver}: no cached car/position coverage", flush=True
                )
                continue
            bundle = fastf1.normalize(session, str(driver))
            selector = {
                "year": item["year"],
                "location": item["location"],
                "session": item["name"],
                "driver": bundle["driver"]["code"],
            }
            bundle["selector"] = selector
            result = store.import_bundles([bundle])[0]
            write_json(
                session_directory(data_dir, selector) / "normalized" / "fastf1.json",
                bundle,
            )
            if not track_saved:
                try:
                    geometry = build_track(bundle)
                except DataError:
                    pass
                else:
                    store.save_track(result["session_id"], geometry)
                    track_saved = True
            print(
                f"  {bundle['driver']['code']}: {len(bundle['positions']):,} positions, {len(bundle['telemetry']):,} car samples",
                flush=True,
            )
        if not track_saved:
            raise DataError(
                f"Could not build the track for {item['id']} from cached data."
            )
    print(
        "Replay preparation complete. No provider downloads were requested.", flush=True
    )
