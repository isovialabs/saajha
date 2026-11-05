"""Import rides recorded with a phone GPS app (GPX files) into the pipeline's positions format."""
from pathlib import Path

import gpxpy
import pandas as pd


def read_gpx(path):
    """All timestamped points in a GPX file as a DataFrame (lat, lon, timestamp in unix seconds)."""
    with open(path, encoding="utf-8") as f:
        gpx = gpxpy.parse(f)
    rows = [(p.latitude, p.longitude, int(p.time.timestamp()))
            for track in gpx.tracks for seg in track.segments for p in seg.points if p.time]
    return pd.DataFrame(rows, columns=["lat", "lon", "timestamp"])


def resample(trace, seconds=15):
    """Keep one point per `seconds` window. Phones log every second, but the pipeline's
    settings (e.g. "moved < 30 m between readings") were tuned on 30-second bus data."""
    trace = trace.sort_values("timestamp")
    return trace.groupby(trace.timestamp // seconds).head(1)


def import_gpx(folder, out, seconds=15):
    """Read every .gpx file in `folder` into one positions CSV. Each file is one ride."""
    files = sorted(Path(folder).glob("*.gpx"))
    if not files:
        raise SystemExit(f"No .gpx files found in {folder}")
    rides = []
    for f in files:
        ride = resample(read_gpx(f), seconds)
        print(f"{f.name}: {len(ride)} points")
        rides.append(ride.assign(vehicle_id=f.stem, route_id=None))
    df = pd.concat(rides, ignore_index=True)[["vehicle_id", "route_id", "lat", "lon", "timestamp"]]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"{len(files)} rides, {len(df):,} points -> {out}")
    return df
