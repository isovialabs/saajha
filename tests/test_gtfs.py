import numpy as np
import pandas as pd

from saajha.gtfs import build_gtfs
from saajha.routes import cluster_routes, trace_tokens
from saajha.stops import detect_stops, find_dwell_points

REQUIRED = {
    "agency.txt": {"agency_name", "agency_url", "agency_timezone"},
    "stops.txt": {"stop_id", "stop_lat", "stop_lon"},
    "routes.txt": {"route_id", "route_type"},
    "trips.txt": {"route_id", "service_id", "trip_id"},
    "stop_times.txt": {"trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"},
    "frequencies.txt": {"trip_id", "start_time", "end_time", "headway_secs"},
    "calendar.txt": {"service_id", "start_date", "end_date"},
}


def make_rides():
    """Two corridors, each ridden 4x northbound; vehicles pause 90 s at 3 shared stops."""
    rows = []
    for r, lon in enumerate([77.20, 77.30]):
        for v in range(4):
            lat, ts = 28.60, 1_700_000_000 + v * 300
            for k in range(40):
                if k not in (10, 11, 20, 21, 30, 31, 32):  # pauses
                    lat += 0.0012
                rows.append((f"V{r}{v}", lat + np.random.default_rng(k).normal(0, 1e-5), lon, ts))
                ts += 30
    return pd.DataFrame(rows, columns=["vehicle_id", "lat", "lon", "timestamp"])


def test_build_gtfs_writes_valid_feed(tmp_path):
    rides = make_rides()
    stops = detect_stops(find_dwell_points(rides), min_vehicles=2)
    labels = cluster_routes(trace_tokens(rides), threshold=0.5)
    summary = build_gtfs(rides, labels, stops, tmp_path / "gtfs")

    assert summary["routes"] == 2
    for name, cols in REQUIRED.items():
        df = pd.read_csv(tmp_path / "gtfs" / name)
        assert cols <= set(df.columns), name
        assert len(df) > 0, name

    st = pd.read_csv(tmp_path / "gtfs" / "stop_times.txt")
    stop_ids = set(pd.read_csv(tmp_path / "gtfs" / "stops.txt").stop_id)
    assert set(st.stop_id) <= stop_ids
    for _, g in st.groupby("trip_id"):
        assert len(g) >= 2
        assert list(g.stop_sequence) == sorted(g.stop_sequence)
        assert list(g.arrival_time) == sorted(g.arrival_time)
    assert (tmp_path / "gtfs.zip").exists()
