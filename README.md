# Saajha
Mapping Delhi's shared e-rickshaw network with GPS traces and ML.

## Status
Building and testing the pipeline on Delhi's live bus GPS feed (Open Transit Data Delhi) before collecting e-rickshaw data.

## Results so far: stop detection on live bus GPS
Data: ~1 hour of live positions for ~5,900 Delhi buses, scored against the official bus stop list (2023 GTFS).

| min buses pausing | detected stops | within 50 m of a real stop | within 100 m |
|---|---|---|---|
| 2 | 769 | 45% | 66% |
| 3 | 567 | 49% | 71% |
| 5 | 298 | 47% | 74% |

Next: filter out traffic signals using OpenStreetMap.

Removing detections within 40 m of an OpenStreetMap traffic signal raised precision from 49% to 53% (within 50 m) and from 71% to 75% (within 100 m), at the cost of 87 stops. Gains are limited because OSM maps only ~1,500 signals in Delhi, far fewer than actually exist.