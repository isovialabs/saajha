"""Bus service at metro stations, summarised per time of day for the public map.

docs/service.json keeps, for each time slot (morning / midday / night), buses per hour at every
station for each of the last few days, plus their average. Each automatic collection run adds
one day to one slot.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from saajha.geo import EARTH_RADIUS_KM

R_M = EARTH_RADIUS_KM * 1000
IST = "Asia/Kolkata"
AIRPORT = "Indira Gandhi International Airport"  # buses use terminal bays, not street stops


def load_stations(path):
    """Stations from the site's stations.geojson as a DataFrame (name, lat, lon, bus_stops_500m)."""
    geo = json.loads(Path(path).read_text(encoding="utf-8"))
    return pd.DataFrame([{"name": f["properties"]["name"],
                          "bus_stops_500m": f["properties"].get("bus_stops_500m", 0),
                          "lon": f["geometry"]["coordinates"][0],
                          "lat": f["geometry"]["coordinates"][1]} for f in geo["features"]])


def buses_per_hour(pos, stations, radius_m=300):
    """Distinct vehicles seen within radius_m of each station, per hour of observation."""
    hours = max((pos.timestamp.max() - pos.timestamp.min()) / 3600, 1 / 60)
    tree = BallTree(np.radians(pos[["lat", "lon"]].values), metric="haversine")
    idx = tree.query_radius(np.radians(stations[["lat", "lon"]].values), r=radius_m / R_M)
    vids = pos.vehicle_id.values
    return np.array([len(set(vids[i])) for i in idx]) / hours


def classify(names, stops_500m, bph):
    """Same rule as the notebook: no bus network nearby / buses miss the station / well served."""
    q = np.quantile(bph, 0.25)
    out = []
    for name, s, b in zip(names, stops_500m, bph):
        if name == AIRPORT:
            out.append("served")
        elif s == 0 and b < 5:
            out.append("none")
        else:
            out.append("missed" if b <= q else "served")
    return out


def update_service(service_path, slot, pos, stations, keep_days=7):
    """Add today's measurement for `slot` to service.json and recompute its averages."""
    path = Path(service_path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.setdefault("slots", {})

    bph = buses_per_hour(pos, stations)
    start = pd.to_datetime(pos.timestamp.min(), unit="s", utc=True).tz_convert(IST)
    end = pd.to_datetime(pos.timestamp.max(), unit="s", utc=True).tz_convert(IST)

    s = data["slots"].setdefault(slot, {"days": {}})
    s["days"][start.strftime("%Y-%m-%d")] = {
        "window": f"{start:%H:%M}-{end:%H:%M}",
        "vehicles": int(pos.vehicle_id.nunique()),
        "bph": [round(float(x), 1) for x in bph],
    }
    for day in sorted(s["days"])[:-keep_days]:      # keep only the most recent days
        del s["days"][day]

    names = stations.name.tolist()
    days = [d for d in s["days"].values() if len(d["bph"]) == len(names)]  # skip days from an older station list
    avg = np.mean([d["bph"] for d in days], axis=0)
    gaps = classify(names, stations.bus_stops_500m.values, avg)
    s.update({
        "n_days": len(days),
        "window": days[-1]["window"],
        "vehicles": int(np.mean([d["vehicles"] for d in days])),
        "stations": {n: [round(float(b), 1), g] for n, b, g in zip(names, avg, gaps)},
    })
    data["updated_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return s
