"""Nearest bus stops to each metro station: "how do I get out of here?"

docs/nearby.json lists, for every station, the official bus stops within walking distance,
with straight-line distance, an estimated walking time and buses per hour passing each stop.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from saajha.geo import EARTH_RADIUS_KM

R_M = EARTH_RADIUS_KM * 1000
DETOUR = 1.3            # streets are longer than the straight line
WALK_M_PER_MIN = 80     # about 4.8 km/h


def stop_buses_per_hour(pos, stops, radius_m=150):
    """Distinct vehicles passing within radius_m of each stop, per hour. 150 m because buses
    report every ~30 s (~250 m apart at city speed), so a passing bus lands at least one point
    inside a 300 m-wide circle."""
    hours = max((pos.timestamp.max() - pos.timestamp.min()) / 3600, 1 / 60)
    tree = BallTree(np.radians(pos[["lat", "lon"]].values), metric="haversine")
    idx = tree.query_radius(np.radians(stops[["lat", "lon"]].values), r=radius_m / R_M)
    vids = pos.vehicle_id.values
    return np.array([len(set(vids[i])) for i in idx]) / hours


def build_nearby(stations, gtfs_stops, pos=None, radius_m=600, max_stops=6):
    """For each station, up to max_stops GTFS bus stops within radius_m, nearest first."""
    gs = gtfs_stops.rename(columns={"stop_lat": "lat", "stop_lon": "lon"}).reset_index(drop=True)
    gs["stop_id"] = gs["stop_id"].astype(str)
    tree = BallTree(np.radians(gs[["lat", "lon"]].values), metric="haversine")
    idx, dist = tree.query_radius(np.radians(stations[["lat", "lon"]].values), r=radius_m / R_M,
                                  return_distance=True, sort_results=True)
    used = sorted({int(j) for i in idx for j in i[:max_stops]})
    bph = dict(zip(used, stop_buses_per_hour(pos, gs.loc[used]))) if pos is not None and used else {}

    out = {}
    for name, ii, dd in zip(stations.name, idx, dist):
        out[name] = [{
            "id": gs.stop_id[j], "name": str(gs.stop_name[j]).strip(),
            "lat": round(float(gs.lat[j]), 6), "lon": round(float(gs.lon[j]), 6),
            "dist_m": int(round(d * R_M)),
            "walk_min": max(1, int(round(d * R_M * DETOUR / WALK_M_PER_MIN))),
            **({"bph": round(float(bph[j]), 1)} if j in bph else {}),
        } for j, d in zip(ii[:max_stops], dd[:max_stops])]
    return {"radius_m": radius_m, "stations": out}


def write_nearby(path, nearby):
    Path(path).write_text(json.dumps(nearby, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def load_nearby_stops(path):
    """All distinct stops referenced in nearby.json, as a DataFrame (stop_id, lat, lon)."""
    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    rows = {s["id"]: (s["lat"], s["lon"]) for stops in data["stations"].values() for s in stops}
    if not rows:
        return None
    return pd.DataFrame([(k, *v) for k, v in rows.items()], columns=["stop_id", "lat", "lon"])
