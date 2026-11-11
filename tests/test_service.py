import json

import numpy as np
import pandas as pd

from saajha.service import update_service


def stations():
    return pd.DataFrame({"name": ["Busy", "Quiet", "Empty", "Mid", "Missed"],
                         "lat": [28.60, 28.65, 28.70, 28.62, 28.75], "lon": [77.20, 77.20, 77.20, 77.25, 77.20],
                         "bus_stops_500m": [5, 4, 0, 3, 2]})


def positions(day, n_busy):
    """Buses passing near 'Busy' (n_busy), 'Mid' (4) and 'Quiet' (1); none near 'Empty'; one hour."""
    t0 = int(pd.Timestamp(f"{day} 09:00", tz="Asia/Kolkata").timestamp())
    rows = []
    for name, lat, lon, n in [("Busy", 28.60, 77.20, n_busy), ("Mid", 28.62, 77.25, 4), ("Quiet", 28.65, 77.20, 1)]:
        for v in range(n):
            rows += [(f"{name}{v}", lat, lon, t0), (f"{name}{v}", lat + 0.01, lon, t0 + 3600)]
    return pd.DataFrame(rows, columns=["vehicle_id", "lat", "lon", "timestamp"])


def test_update_service_averages_days_and_classifies(tmp_path):
    out = tmp_path / "service.json"
    update_service(out, "morning", positions("2026-11-10", 10), stations())
    s = update_service(out, "morning", positions("2026-11-11", 20), stations())

    data = json.loads(out.read_text())
    assert s["n_days"] == 2 and s["window"] == "09:00-10:00"
    assert data["slots"]["morning"]["stations"]["Busy"] == [15.0, "served"]   # mean of 10 and 20
    assert data["slots"]["morning"]["stations"]["Empty"] == [0.0, "none"]      # no stops, no buses
    assert data["slots"]["morning"]["stations"]["Missed"] == [0.0, "missed"]   # stops nearby, no buses at station
    assert data["slots"]["morning"]["stations"]["Mid"][1] == "served"


def test_update_service_keeps_only_recent_days(tmp_path):
    out = tmp_path / "service.json"
    for d in range(1, 10):
        update_service(out, "night", positions(f"2026-11-{d:02d}", 5), stations(), keep_days=7)
    days = json.loads(out.read_text())["slots"]["night"]["days"]
    assert len(days) == 7 and min(days) == "2026-11-03"
