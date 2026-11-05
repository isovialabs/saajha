import numpy as np


def haversine_km(lat1, lon1, lat2, lon2):
    """Distance in km between two lat/lon points (works on arrays too)."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = np.sin((lat2 - lat1) / 2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2)**2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


def remove_jumps(t, max_km=1.0):
    """Drop GPS glitches: points more than max_km from the median of their 5 neighbors in time."""
    t = t.sort_values("timestamp")
    med_lat = t.lat.rolling(5, center=True, min_periods=1).median()
    med_lon = t.lon.rolling(5, center=True, min_periods=1).median()
    dist = haversine_km(t.lat, t.lon, med_lat, med_lon)
    return t[dist < max_km]