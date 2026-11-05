import numpy as np
import pandas as pd

from saajha.clean import remove_jumps
from saajha.geo import bearing_deg, haversine_km
from saajha.routes import cluster_routes, trace_tokens
from saajha.stops import detect_stops, find_dwell_points


def make_trace(vid, lats, lons, start=0, step_s=30):
    return pd.DataFrame({"vehicle_id": vid, "lat": lats, "lon": lons,
                         "timestamp": start + step_s * np.arange(len(lats))})


def test_haversine_one_degree_latitude():
    assert abs(haversine_km(28.0, 77.0, 29.0, 77.0) - 111.2) < 0.5


def test_bearing_north_and_east():
    assert abs(bearing_deg(28.0, 77.0, 28.1, 77.0) - 0) < 1
    assert abs(bearing_deg(28.0, 77.0, 28.0, 77.1) - 90) < 1


def test_remove_jumps_drops_teleport():
    lats = np.linspace(28.60, 28.61, 11)
    lats[5] = 28.90  # 30 km glitch
    t = make_trace("bus", lats, np.full(11, 77.2))
    out = remove_jumps(t)
    assert len(out) == 10 and 28.90 not in out.lat.values


def test_stop_detected_where_several_buses_pause():
    frames = []
    for i in range(3):
        lats = np.r_[np.linspace(28.600, 28.605, 5), np.full(4, 28.605), np.linspace(28.605, 28.610, 5)]
        frames.append(make_trace(f"bus{i}", lats, np.full(len(lats), 77.2), start=i * 1000))
    stops = detect_stops(find_dwell_points(pd.concat(frames)), min_vehicles=3)
    assert len(stops) == 1
    assert haversine_km(stops.lat[0], stops.lon[0], 28.605, 77.2) < 0.03


def test_opposite_directions_get_different_routes():
    north = np.linspace(28.60, 28.65, 30)
    traces = pd.concat([
        make_trace("n1", north, np.full(30, 77.2)),
        make_trace("n2", north, np.full(30, 77.2), start=60),
        make_trace("s1", north[::-1], np.full(30, 77.2)),
        make_trace("s2", north[::-1], np.full(30, 77.2), start=60),
    ])
    labels = cluster_routes(trace_tokens(traces, use_direction=True), threshold=0.5)
    assert labels["n1"] == labels["n2"] != -1
    assert labels["s1"] == labels["s2"] != -1
    assert labels["n1"] != labels["s1"]
