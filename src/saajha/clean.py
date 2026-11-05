"""GPS cleaning."""
import pandas as pd

from saajha.geo import haversine_km  # re-exported so `from saajha.clean import haversine_km` still works


def remove_jumps(t, max_km=1.0):
    """Drop GPS glitches from one vehicle's trace: points more than max_km
    from the median position of their 5 neighbours in time."""
    t = t.sort_values("timestamp")
    med_lat = t.lat.rolling(5, center=True, min_periods=1).median()
    med_lon = t.lon.rolling(5, center=True, min_periods=1).median()
    dist = haversine_km(t.lat, t.lon, med_lat, med_lon)
    return t[dist < max_km]


def clean_positions(pos, max_km=1.0):
    """Deduplicate a positions table and remove GPS jumps for every vehicle."""
    pos = pos.drop_duplicates(["vehicle_id", "timestamp"])
    return pd.concat([remove_jumps(g, max_km) for _, g in pos.groupby("vehicle_id")], ignore_index=True)
