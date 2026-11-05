"""Stop detection: find places where vehicles repeatedly stand still."""
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.neighbors import BallTree

from saajha.geo import EARTH_RADIUS_KM, haversine_km


def find_dwell_points(clean, max_step_km=0.03, max_gap_s=120):
    """Points where a vehicle moved less than max_step_km before its next reading."""
    clean = clean.sort_values(["vehicle_id", "timestamp"]).reset_index(drop=True)
    nxt = clean.groupby("vehicle_id")[["lat", "lon", "timestamp"]].shift(-1)
    step_km = haversine_km(clean.lat, clean.lon, nxt.lat, nxt.lon)
    gap_s = nxt.timestamp - clean.timestamp
    return clean[(step_km < max_step_km) & (gap_s <= max_gap_s)]


def detect_stops(dwell, eps_m=30, min_samples=3, min_vehicles=3):
    """Cluster dwell points; a stop is a cluster where at least min_vehicles different vehicles paused."""
    if dwell.empty:
        return pd.DataFrame(columns=["lat", "lon", "n_points", "n_vehicles"])
    coords = np.radians(dwell[["lat", "lon"]].values)
    labels = DBSCAN(eps=eps_m / 1000 / EARTH_RADIUS_KM, min_samples=min_samples,
                    metric="haversine", algorithm="ball_tree").fit_predict(coords)
    stops = (dwell.assign(cluster=labels)
             .query("cluster >= 0")
             .groupby("cluster")
             .agg(lat=("lat", "mean"), lon=("lon", "mean"),
                  n_points=("lat", "size"), n_vehicles=("vehicle_id", "nunique")))
    return stops[stops.n_vehicles >= min_vehicles].reset_index(drop=True)


def nearest_distance_m(points, ref_lat, ref_lon):
    """Distance in metres from each row of `points` (lat, lon) to the nearest reference point."""
    tree = BallTree(np.radians(np.c_[ref_lat, ref_lon]), metric="haversine")
    dist, _ = tree.query(np.radians(points[["lat", "lon"]].values), k=1)
    return dist[:, 0] * EARTH_RADIUS_KM * 1000


def score_stops(detected, true_stops, coverage_m=500):
    """Precision of detected stops against known stops (e.g. GTFS stops.txt).
    Detections more than coverage_m from any known stop are treated as outside coverage."""
    d = nearest_distance_m(detected, true_stops.stop_lat.values, true_stops.stop_lon.values)
    d = d[d <= coverage_m]
    return {
        "stops_scored": int(len(d)),
        "within_50m": float((d <= 50).mean()) if len(d) else float("nan"),
        "within_100m": float((d <= 100).mean()) if len(d) else float("nan"),
    }
