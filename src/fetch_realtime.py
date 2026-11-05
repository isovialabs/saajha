import os, requests
import pandas as pd
from dotenv import load_dotenv
from google.transit import gtfs_realtime_pb2

load_dotenv()
KEY = os.getenv("OTD_API_KEY")
URL = f"https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb?key={KEY}"

resp = requests.get(URL, timeout=30)
resp.raise_for_status()

feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(resp.content)

rows = []
for e in feed.entity:
    if e.HasField("vehicle"):
        v = e.vehicle
        rows.append({
            "vehicle_id": v.vehicle.id,
            "route_id": v.trip.route_id,
            "lat": v.position.latitude,
            "lon": v.position.longitude,
            "speed": v.position.speed,
            "timestamp": v.timestamp,
        })

df = pd.DataFrame(rows)
print(f"{len(df)} buses live right now")
print(df.head())