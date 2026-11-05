"""Collect live vehicle positions from Delhi's Open Transit Data feed."""
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from google.transit import gtfs_realtime_pb2

FEED_URL = "https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb?key={key}"


def fetch_positions(key):
    """Download one snapshot of the live feed and return it as a DataFrame."""
    resp = requests.get(FEED_URL.format(key=key), timeout=30)
    resp.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return pd.DataFrame([{
        "vehicle_id": e.vehicle.vehicle.id,
        "route_id": e.vehicle.trip.route_id,
        "lat": e.vehicle.position.latitude,
        "lon": e.vehicle.position.longitude,
        "timestamp": e.vehicle.timestamp,
    } for e in feed.entity if e.HasField("vehicle")])


def collect(minutes=60, interval=30, out_dir="data/raw"):
    """Poll the feed every `interval` seconds for `minutes` minutes, appending to one CSV."""
    load_dotenv()
    key = os.getenv("OTD_API_KEY")
    if not key:
        raise SystemExit("OTD_API_KEY not found. Put it in a .env file in the project folder.")

    out = Path(out_dir) / f"bus_positions_{datetime.now():%Y%m%d_%H%M}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    end = time.time() + minutes * 60

    while time.time() < end:
        try:
            df = fetch_positions(key)
            if len(df):
                df.to_csv(out, mode="a", header=not out.exists(), index=False)
            print(f"{datetime.now():%H:%M:%S}  saved {len(df)} rows")
        except Exception as e:  # the public feed drops connections now and then; keep going
            print(f"{datetime.now():%H:%M:%S}  error: {e}")
        time.sleep(interval)

    print(f"done -> {out}")
    return out


if __name__ == "__main__":
    collect()
