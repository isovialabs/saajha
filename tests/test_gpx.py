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


RECORDER_GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Saajha ride recorder" xmlns="http://www.topografix.com/GPX/1/1">
  <wpt lat="28.5930" lon="77.0410"><time>2026-11-05T09:00:40Z</time><name>stop</name></wpt>
  <trk><name>Saajha ride</name>
    <desc>{&quot;station&quot;:&quot;Dwarka Sector 12&quot;,&quot;fare_inr&quot;:&quot;10&quot;,&quot;destination&quot;:&quot;Sector 7 &lt;market&gt;&quot;}</desc>
    <trkseg>
      <trkpt lat="28.5922" lon="77.0407"><time>2026-11-05T09:00:00Z</time></trkpt>
      <trkpt lat="28.5930" lon="77.0410"><time>2026-11-05T09:00:40Z</time></trkpt>
    </trkseg></trk>
</gpx>"""


def test_import_reads_recorder_details_and_marks(tmp_path):
    (tmp_path / "ride_a.gpx").write_text(RECORDER_GPX, encoding="utf-8")
    import_gpx(tmp_path, tmp_path / "rides.csv")
    import pandas as pd
    details = pd.read_csv(tmp_path / "rides_details.csv")
    marks = pd.read_csv(tmp_path / "rides_marks.csv")
    assert details.loc[0, "station"] == "Dwarka Sector 12"
    assert details.loc[0, "fare_inr"] == 10
    assert details.loc[0, "destination"] == "Sector 7 <market>"
    assert len(marks) == 1 and marks.loc[0, "ride"] == "ride_a"
