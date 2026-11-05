import os, time, requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from google.transit import gtfs_realtime_pb2

load_dotenv()
URL = f"https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb?key={os.getenv('OTD_API_KEY')}"
OUT = f"data/raw/bus_positions_{datetime.now():%Y%m%d_%H%M}.csv"
POLL_SECONDS = 30
DURATION_MINUTES = 60

def fetch():
    resp = requests.get(URL, timeout=30)
    resp.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return [{
        "vehicle_id": e.vehicle.vehicle.id,
        "route_id": e.vehicle.trip.route_id,
        "lat": e.vehicle.position.latitude,
        "lon": e.vehicle.position.longitude,
        "timestamp": e.vehicle.timestamp,
    } for e in feed.entity if e.HasField("vehicle")]

end = time.time() + DURATION_MINUTES * 60
first = True
while time.time() < end:
    try:
        df = pd.DataFrame(fetch())
        df.to_csv(OUT, mode="a", header=first, index=False)
        first = False
        print(f"{datetime.now():%H:%M:%S}  saved {len(df)} rows")
    except Exception as e:
        print("error:", e)
    time.sleep(POLL_SECONDS)