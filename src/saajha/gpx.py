"""Import rides recorded with a phone GPS app (GPX files) into the pipeline's positions format.

Rides from the Saajha web recorder also carry ride details (station, fare, wait, destination)
as JSON in the track description, and passenger pickup/drop points as waypoints named "stop".
"""
import json
from pathlib import Path

import gpxpy
import pandas as pd


def _parse(path):
    with open(path, encoding="utf-8") as f:
        return gpxpy.parse(f)


def read_gpx(path):
    """All timestamped points in a GPX file as a DataFrame (lat, lon, timestamp in unix seconds)."""
    gpx = _parse(path)
    rows = [(p.latitude, p.longitude, int(p.time.timestamp()))
            for track in gpx.tracks for seg in track.segments for p in seg.points if p.time]
    return pd.DataFrame(rows, columns=["lat", "lon", "timestamp"])


def read_ride_details(path):
    """Ride details and marked stops from a Saajha recorder file. Other GPX files give an empty dict
    and whatever waypoints they contain."""
    gpx = _parse(path)
    details = {}
    for track in gpx.tracks:
        try:
            details = json.loads(track.description or "")
            break
        except (ValueError, TypeError):
            continue
    marks = [(w.latitude, w.longitude, int(w.time.timestamp()) if w.time else None)
             for w in gpx.waypoints if (w.name or "").lower() == "stop"]
    return details, pd.DataFrame(marks, columns=["lat", "lon", "timestamp"])


def resample(trace, seconds=15):
    """Keep one point per `seconds` window. Phones log every second, but the pipeline's
    settings (e.g. "moved < 30 m between readings") were tuned on 30-second bus data."""
    trace = trace.sort_values("timestamp")
    return trace.groupby(trace.timestamp // seconds).head(1)


def import_gpx(folder, out, seconds=15):
    """Read every .gpx file in `folder` into one positions CSV (each file is one ride),
    plus <out>_details.csv (one row per ride) and <out>_marks.csv (marked pickup/drop points)."""
    files = sorted(Path(folder).glob("*.gpx"))
    if not files:
        raise SystemExit(f"No .gpx files found in {folder}")
    rides, details, marks = [], [], []
    for f in files:
        ride = resample(read_gpx(f), seconds)
        info, m = read_ride_details(f)
        print(f"{f.name}: {len(ride)} points, {len(m)} marked stops"
              + (f", from {info['station']}" if info.get("station") else ""))
        rides.append(ride.assign(vehicle_id=f.stem, route_id=None))
        details.append({"ride": f.stem, "points": len(ride), **info})
        marks.append(m.assign(ride=f.stem))

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.concat(rides, ignore_index=True)[["vehicle_id", "route_id", "lat", "lon", "timestamp"]]
    df.to_csv(out, index=False)
    pd.DataFrame(details).to_csv(out.with_name(out.stem + "_details.csv"), index=False)
    pd.concat(marks, ignore_index=True).to_csv(out.with_name(out.stem + "_marks.csv"), index=False)
    print(f"{len(files)} rides, {len(df):,} points -> {out} (+ _details.csv, _marks.csv)")
    return df
