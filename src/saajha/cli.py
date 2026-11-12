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


def cmd_export_gtfs(args):
    from saajha.gtfs import build_gtfs
    from saajha.routes import cluster_routes, moving_vehicles, trace_tokens
    from saajha.stops import detect_stops, find_dwell_points
    clean = load_clean(args.positions)
    stops = detect_stops(find_dwell_points(clean), min_vehicles=args.min_vehicles)
    trace = moving_vehicles(clean, min_span_km=args.min_span_km)
    labels = cluster_routes(trace_tokens(trace), threshold=args.threshold)
    print(f"{len(stops):,} stops, {labels[labels >= 0].nunique():,} route clusters")
    s = build_gtfs(trace, labels, stops, args.out, agency_name=args.agency, route_type=args.route_type)
    print(f"GTFS: {s['routes']:,} routes, {s['stops']:,} stops ({s['skipped']:,} clusters skipped: "
          f"fewer than 2 stops) -> {s['zip']}")


def cmd_nearby(args):
    from saajha.nearby import build_nearby, write_nearby
    from saajha.service import load_stations
    stations = load_stations(args.stations)
    gtfs = pd.read_csv(Path(args.gtfs) / "stops.txt", dtype={"stop_id": str})
    pos = load_clean(args.positions) if args.positions or glob.glob("data/raw/bus_positions_*.csv") else None
    nearby = build_nearby(stations, gtfs, pos, radius_m=args.radius)
    write_nearby(args.out, nearby)
    counts = [len(v) for v in nearby["stations"].values()]
    print(f"{len(counts)} stations, {sum(counts):,} nearby stops, {counts.count(0)} with none within "
          f"{args.radius} m -> {args.out}")


def cmd_summarize(args):
    from saajha.nearby import load_nearby_stops
    from saajha.service import load_stations, update_service
    s = update_service(args.out, args.slot, load_clean(args.positions), load_stations(args.stations),
                       nearby_stops=load_nearby_stops(args.nearby))
    gaps = [g for _, g in s["stations"].values()]
    print(f"{args.slot}: {s['n_days']} day(s), Delhi {s['window']}, ~{s['vehicles']:,} buses | "
          f"{gaps.count('none')} no bus nearby, {gaps.count('missed')} bus misses station -> {args.out}")


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

    x = sub.add_parser("export-gtfs", help="detect stops and routes, then write a GTFS feed")
    x.add_argument("--positions", help="CSV of positions (default: latest in data/raw)")
    x.add_argument("--out", default="data/processed/gtfs")
    x.add_argument("--min-vehicles", type=int, default=3)
    x.add_argument("--threshold", type=float, default=0.7)
    x.add_argument("--min-span-km", type=float, default=2.0)
    x.add_argument("--agency", default="Saajha")
    x.add_argument("--route-type", type=int, default=3, help="GTFS route_type (3 = bus)")
    x.set_defaults(func=cmd_export_gtfs)

    n = sub.add_parser("nearby", help="list the bus stops within walking distance of each metro station")
    n.add_argument("--gtfs", default="data/raw/delhi_bus_gtfs", help="GTFS folder with stops.txt")
    n.add_argument("--positions", help="CSV of positions for buses/hr (default: latest in data/raw)")
    n.add_argument("--stations", default="docs/stations.geojson")
    n.add_argument("--out", default="docs/nearby.json")
    n.add_argument("--radius", type=int, default=600, help="walking radius in metres")
    n.set_defaults(func=cmd_nearby)

    m = sub.add_parser("summarize", help="add bus service at metro stations to the site's service.json")
    m.add_argument("--slot", required=True, choices=["morning", "midday", "night"])
    m.add_argument("--positions", help="CSV of positions (default: latest in data/raw)")
    m.add_argument("--stations", default="docs/stations.geojson")
    m.add_argument("--out", default="docs/service.json")
    m.add_argument("--nearby", default="docs/nearby.json", help="also track buses at these stops, if the file exists")
    m.set_defaults(func=cmd_summarize)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
