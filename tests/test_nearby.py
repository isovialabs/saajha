import json

import pandas as pd

from saajha.nearby import build_nearby, load_nearby_stops, write_nearby
from saajha.service import update_service


def stations():
    return pd.DataFrame({"name": ["A", "B"], "lat": [28.600, 28.700], "lon": [77.200, 77.200],
                         "bus_stops_500m": [2, 0]})


def gtfs_stops():
    # two stops near A (~110 m and ~330 m), one far away; none near B
    return pd.DataFrame({"stop_id": ["10", "11", "12"], "stop_name": ["Near A", "Further A", "Far"],
                         "stop_lat": [28.601, 28.603, 28.650], "stop_lon": [77.200, 77.200, 77.200]})


def positions():
    # 3 buses pass the 'Near A' stop during one hour
    rows = []
    for v in range(3):
        rows += [(f"b{v}", 28.601, 77.200, 0), (f"b{v}", 28.640, 77.200, 3600)]
    return pd.DataFrame(rows, columns=["vehicle_id", "lat", "lon", "timestamp"])


def test_build_nearby_orders_stops_and_counts_buses(tmp_path):
    nb = build_nearby(stations(), gtfs_stops(), positions(), radius_m=600)
    a = nb["stations"]["A"]
    assert [s["name"] for s in a] == ["Near A", "Further A"]       # nearest first, far stop excluded
    assert 100 < a[0]["dist_m"] < 120 and a[0]["walk_min"] >= 1
    assert a[0]["bph"] == 3.0 and a[1]["bph"] == 0.0
    assert nb["stations"]["B"] == []

    write_nearby(tmp_path / "nearby.json", nb)
    ns = load_nearby_stops(tmp_path / "nearby.json")
    assert set(ns.stop_id) == {"10", "11"}


def test_summarize_tracks_nearby_stops(tmp_path):
    nb = build_nearby(stations(), gtfs_stops(), None)
    write_nearby(tmp_path / "nearby.json", nb)
    s = update_service(tmp_path / "service.json", "midday", positions(), stations(),
                       nearby_stops=load_nearby_stops(tmp_path / "nearby.json"))
    assert s["stops"] == {"10": 3.0, "11": 0.0}
    assert "stop_bph" in next(iter(json.loads((tmp_path / "service.json").read_text())["slots"]["midday"]["days"].values()))
