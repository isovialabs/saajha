"""Export detected routes and stops as a GTFS feed (the standard format transit apps read).

Informal transit has no timetable: vehicles leave when full. So each route becomes one
template trip plus a frequencies.txt entry ("about every N minutes between X and Y")
instead of a fixed schedule.
"""
import math
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from saajha.geo import EARTH_RADIUS_KM

R_M = EARTH_RADIUS_KM * 1000


def _hms(seconds):
    seconds = int(round(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _local_seconds(ts, tz):
    t = pd.to_datetime(ts, unit="s", utc=True).tz_convert(tz)
    return t.hour * 3600 + t.minute * 60 + t.second


def route_pattern(trace, stops, stop_tree, snap_m=50, on_route_m=80, min_share=0.25):
    """Ordered stop sequence and travel times for one route cluster.

    trace: positions of every vehicle in the cluster. The vehicle with the most points is
    the reference path; a stop is on the route if enough vehicles came within snap_m of it
    and it lies within on_route_m of the reference path. Stops are ordered along the path.
    """
    ref_id = trace.groupby("vehicle_id").size().idxmax()
    ref = trace[trace.vehicle_id == ref_id].sort_values("timestamp").reset_index(drop=True)

    visits = {}
    for vid, g in trace.groupby("vehicle_id"):
        idx = stop_tree.query_radius(np.radians(g[["lat", "lon"]].values), r=snap_m / R_M)
        for sid in set(np.concatenate(idx)) if len(idx) else ():
            visits[sid] = visits.get(sid, 0) + 1
    needed = max(1, math.ceil(min_share * trace.vehicle_id.nunique()))
    candidates = [sid for sid, n in visits.items() if n >= needed]
    if len(candidates) < 2:
        return None

    ref_tree = BallTree(np.radians(ref[["lat", "lon"]].values), metric="haversine")
    dist, pos = ref_tree.query(np.radians(stops.loc[candidates, ["lat", "lon"]].values), k=1)
    seq = pd.DataFrame({"stop_id": candidates, "dist_m": dist[:, 0] * R_M, "ref_idx": pos[:, 0]})
    seq = seq[seq.dist_m <= on_route_m].sort_values("ref_idx").drop_duplicates("ref_idx")
    if len(seq) < 2:
        return None
    seq["offset_s"] = ref.timestamp.values[seq.ref_idx] - ref.timestamp.values[seq.ref_idx.iloc[0]]
    return {"stops": seq[["stop_id", "offset_s"]].reset_index(drop=True),
            "shape": ref[["lat", "lon"]], "n_vehicles": trace.vehicle_id.nunique()}


def build_gtfs(clean, labels, stops, out_dir, agency_name="Saajha", agency_url="https://isovialabs.github.io/saajha/",
               tz="Asia/Kolkata", route_type=3):
    """Write a GTFS feed to out_dir and return a summary dict.

    clean: cleaned positions; labels: Series vehicle_id -> route cluster (-1 = unclustered);
    stops: detected stops (lat, lon), indexed 0..n-1.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stops = stops.reset_index(drop=True)
    stop_tree = BallTree(np.radians(stops[["lat", "lon"]].values), metric="haversine")

    window_h = (clean.timestamp.max() - clean.timestamp.min()) / 3600
    start_s = _local_seconds(clean.timestamp.min(), tz)
    end_s = start_s + int(window_h * 3600)
    first_day = pd.to_datetime(clean.timestamp.min(), unit="s", utc=True).tz_convert(tz)

    routes, trips, stop_times, freqs, shapes, used = [], [], [], [], [], set()
    clustered = labels[labels >= 0]
    for n, (cluster, vids) in enumerate(clustered.groupby(clustered), start=1):
        pattern = route_pattern(clean[clean.vehicle_id.isin(vids.index)], stops, stop_tree)
        if pattern is None:
            continue
        rid, tid, shid = f"R{n}", f"R{n}_t", f"R{n}_s"
        seq = pattern["stops"]
        routes.append({"route_id": rid, "agency_id": "saajha", "route_short_name": rid,
                       "route_long_name": f"S{seq.stop_id.iloc[0]} to S{seq.stop_id.iloc[-1]}",
                       "route_type": route_type})
        trips.append({"route_id": rid, "service_id": "daily", "trip_id": tid, "shape_id": shid})
        for i, s in seq.iterrows():
            t = _hms(start_s + s.offset_s)
            stop_times.append({"trip_id": tid, "arrival_time": t, "departure_time": t,
                               "stop_id": f"S{s.stop_id}", "stop_sequence": i + 1})
            used.add(s.stop_id)
        headway = int(np.clip(window_h * 3600 / pattern["n_vehicles"], 60, 3600))
        freqs.append({"trip_id": tid, "start_time": _hms(start_s), "end_time": _hms(max(end_s, start_s + 60)),
                      "headway_secs": headway, "exact_times": 0})
        for k, (la, lo) in enumerate(pattern["shape"].itertuples(index=False), start=1):
            shapes.append({"shape_id": shid, "shape_pt_lat": round(la, 6), "shape_pt_lon": round(lo, 6),
                           "shape_pt_sequence": k})

    used = sorted(used)
    files = {
        "agency.txt": pd.DataFrame([{"agency_id": "saajha", "agency_name": agency_name,
                                     "agency_url": agency_url, "agency_timezone": tz}]),
        "stops.txt": pd.DataFrame({"stop_id": [f"S{i}" for i in used], "stop_name": [f"Stop {i}" for i in used],
                                   "stop_lat": stops.loc[used, "lat"].round(6).values,
                                   "stop_lon": stops.loc[used, "lon"].round(6).values}),
        "routes.txt": pd.DataFrame(routes),
        "trips.txt": pd.DataFrame(trips),
        "stop_times.txt": pd.DataFrame(stop_times),
        "frequencies.txt": pd.DataFrame(freqs),
        "shapes.txt": pd.DataFrame(shapes),
        "calendar.txt": pd.DataFrame([{"service_id": "daily", **{d: 1 for d in
                                       ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]},
                                       "start_date": first_day.strftime("%Y%m%d"),
                                       "end_date": (first_day + pd.Timedelta(days=365)).strftime("%Y%m%d")}]),
    }
    for name, df in files.items():
        df.to_csv(out / name, index=False)
    with zipfile.ZipFile(out.with_suffix(".zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(out / name, name)
    return {"routes": len(routes), "stops": len(used), "skipped": clustered.nunique() - len(routes),
            "zip": str(out.with_suffix(".zip"))}
