"""Route extraction: group vehicles that travel the same path in the same direction."""
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import completeness_score, homogeneity_score

from saajha.geo import bearing_deg, haversine_km

CELL_DEG = 0.0015  # map squares of about 150 m


def moving_vehicles(clean, min_span_km=2.0, min_points=20):
    """Keep only vehicles that actually travelled somewhere."""
    g = clean.groupby("vehicle_id")
    span = haversine_km(g.lat.min(), g.lon.min(), g.lat.max(), g.lon.max())
    keep = span[(span > min_span_km) & (g.size() >= min_points)].index
    return clean[clean.vehicle_id.isin(keep)]


def trace_tokens(trace, cell_deg=CELL_DEG, use_direction=True, min_step_km=0.03):
    """Represent each vehicle's trace as a set of map cells, optionally tagged
    with heading (0=N, 1=E, 2=S, 3=W) so opposite directions don't match."""
    t = trace.sort_values(["vehicle_id", "timestamp"]).reset_index(drop=True)
    t["cell"] = list(zip((t.lat / cell_deg).round().astype(int), (t.lon / cell_deg).round().astype(int)))
    if not use_direction:
        return t.groupby("vehicle_id")["cell"].apply(set)

    nxt = t.groupby("vehicle_id")[["lat", "lon"]].shift(-1)
    step = haversine_km(t.lat, t.lon, nxt.lat, nxt.lon)
    heading = bearing_deg(t.lat, t.lon, nxt.lat, nxt.lon)
    mv = t[heading.notna() & (step > min_step_km)].copy()  # a standing vehicle has no heading
    mv["tok"] = list(zip(mv.cell, ((heading[mv.index] + 45) // 90 % 4).astype(int)))
    return mv.groupby("vehicle_id")["tok"].apply(set)


def overlap_distance(token_sets):
    """1 - (shared tokens / tokens in the shorter trace), for every pair of vehicles."""
    sets = list(token_sets)
    vocab = {tok: i for i, tok in enumerate(set().union(*sets))}
    rows = [r for r, s in enumerate(sets) for _ in s]
    cols = [vocab[tok] for s in sets for tok in s]
    M = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(sets), len(vocab)))
    inter = (M @ M.T).toarray()
    size = np.asarray(M.sum(axis=1)).ravel()
    return 1 - inter / np.minimum.outer(size, size)


def cluster_routes(token_sets, threshold=0.7):
    """Average-linkage clustering of traces. Returns a Series: vehicle_id -> route cluster
    (-1 for vehicles that didn't share a route with anyone)."""
    labels = AgglomerativeClustering(n_clusters=None, metric="precomputed", linkage="average",
                                     distance_threshold=threshold).fit_predict(overlap_distance(token_sets))
    labels = pd.Series(labels, index=token_sets.index, name="route")
    sizes = labels.map(labels.value_counts())
    return labels.where(sizes >= 2, -1)


def score_routes(labels, true_route):
    """Coverage, homogeneity and completeness of route clusters against known route ids."""
    truth = true_route.loc[labels.index]
    m = labels >= 0
    return {
        "clusters": int(labels[m].nunique()),
        "coverage": float(m.mean()),
        "homogeneity": float(homogeneity_score(truth[m], labels[m])) if m.any() else float("nan"),
        "completeness": float(completeness_score(truth[m], labels[m])) if m.any() else float("nan"),
    }
