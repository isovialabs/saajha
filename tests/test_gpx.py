from datetime import datetime, timedelta, timezone

import gpxpy.gpx

from saajha.gpx import import_gpx


def write_gpx(path, n_seconds=120):
    gpx = gpxpy.gpx.GPX()
    seg = gpxpy.gpx.GPXTrackSegment()
    start = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
    for i in range(n_seconds):
        seg.points.append(gpxpy.gpx.GPXTrackPoint(28.60 + i * 1e-5, 77.20, time=start + timedelta(seconds=i)))
    track = gpxpy.gpx.GPXTrack()
    track.segments.append(seg)
    gpx.tracks.append(track)
    path.write_text(gpx.to_xml(), encoding="utf-8")


def test_import_gpx_resamples_and_labels_rides(tmp_path):
    write_gpx(tmp_path / "ride_01.gpx")
    write_gpx(tmp_path / "ride_02.gpx")
    df = import_gpx(tmp_path, tmp_path / "rides.csv", seconds=15)
    assert set(df.vehicle_id) == {"ride_01", "ride_02"}
    assert (df.groupby("vehicle_id").size() == 8).all()  # 120 s of 1-second points -> one per 15 s
    assert df.groupby("vehicle_id").timestamp.diff().max() == 15
