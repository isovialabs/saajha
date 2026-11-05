"""Command line: `saajha collect`, `saajha stops`, `saajha routes`."""
import argparse
import glob
from pathlib import Path

import pandas as pd

from saajha.clean import clean_positions

PROCESSED = Path("data/processed")


def latest_positions():
    files = sorted(glob.glob("data/raw/bus_positions_*.csv"))
    if not files:
        raise SystemExit("No data/raw/bus_positions_*.csv found. Run `saajha collect` first.")
    return files[-1]


def load_clean(path):
    path = path or latest_positions()
    print(f"loading {path}")
    clean = clean_positions(pd.read_csv(path, dtype={"route_id": str}))
    print(f"{len(clean):,} clean points from {clean.vehicle_id.nunique():,} vehicles")
    return clean


def cmd_collect(args):
    from saajha.collect import collect
    collect(minutes=args.minutes, interval=args.interval)


def cmd_import_gpx(args):
    from saajha.gpx import import_gpx
    import_gpx(args.folder, args.out, seconds=args.resample)


def cmd_stops(args):
    from saajha.stops import detect_stops, find_dwell_points, score_stops
    stops = detect_stops(find_dwell_points(load_clean(args.positions)), min_vehicles=args.min_vehicles)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    stops.to_csv(PROCESSED / "stops.csv", index=False)
    print(f"{len(stops):,} stops detected -> {PROCESSED / 'stops.csv'}")
    if args.gtfs:
        s = score_stops(stops, pd.read_csv(Path(args.gtfs) / "stops.txt"))
        print(f"within 50 m: {s['within_50m']:.0%} | within 100 m: {s['within_100m']:.0%} "
              f"({s['stops_scored']:,} stops inside GTFS coverage)")


def cmd_routes(args):
    from saajha.routes import cluster_routes, moving_vehicles, score_routes, trace_tokens
    trace = moving_vehicles(load_clean(args.positions), min_span_km=args.min_span_km)
    tokens = trace_tokens(trace, use_direction=not args.no_direction)
    labels = cluster_routes(tokens, threshold=args.threshold)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    labels.rename_axis("vehicle_id").reset_index().to_csv(PROCESSED / "routes.csv", index=False)
    print(f"{len(tokens):,} moving vehicles -> {PROCESSED / 'routes.csv'}")
    true_route = trace.dropna(subset=["route_id"]).groupby("vehicle_id").route_id.agg(lambda s: s.mode().iat[0])
    labels = labels[labels.index.isin(true_route.index)]
    if len(labels):
        s = score_routes(labels, true_route)
        print(f"{s['clusters']:,} routes | {s['coverage']:.0%} clustered | "
              f"homogeneity {s['homogeneity']:.2f} | completeness {s['completeness']:.2f}")


def main():
    p = argparse.ArgumentParser(prog="saajha", description="Map informal transit routes from GPS traces.")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("collect", help="record live bus positions")
    c.add_argument("--minutes", type=int, default=60)
    c.add_argument("--interval", type=int, default=30, help="seconds between polls")
    c.set_defaults(func=cmd_collect)

    g = sub.add_parser("import-gpx", help="convert phone GPX rides into a positions CSV")
    g.add_argument("folder", help="folder of .gpx files, one per ride")
    g.add_argument("--out", default="data/raw/rides.csv")
    g.add_argument("--resample", type=int, default=15, help="seconds between kept points")
    g.set_defaults(func=cmd_import_gpx)

    s = sub.add_parser("stops", help="detect stops from GPS traces")
    s.add_argument("--positions", help="CSV of positions (default: latest in data/raw)")
    s.add_argument("--gtfs", help="GTFS folder to score against, e.g. data/raw/delhi_bus_gtfs")
    s.add_argument("--min-vehicles", type=int, default=3)
    s.set_defaults(func=cmd_stops)

    r = sub.add_parser("routes", help="extract routes from GPS traces")
    r.add_argument("--positions", help="CSV of positions (default: latest in data/raw)")
    r.add_argument("--threshold", type=float, default=0.7)
    r.add_argument("--no-direction", action="store_true", help="ignore travel direction")
    r.add_argument("--min-span-km", type=float, default=2.0, help="skip traces shorter than this")
    r.set_defaults(func=cmd_routes)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
