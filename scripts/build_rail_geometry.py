"""Rebuild the bundled historical Network Rail geometry; not needed for generation."""

import argparse
import csv
import hashlib
import json
import math
import urllib.request
from pathlib import Path

import networkx as nx
import shapefile
from pyproj import Transformer
from scipy.spatial import cKDTree

COMMIT = "a7c2cece9df7770e68a78cd716604c96ae38cd1a"
BASE = f"https://raw.githubusercontent.com/openraildata/network-rail-gis/{COMMIT}/"
WAYPOINTS = [
    ("London Aggregate Terminal", 51.5174, -0.2672),
    ("Southall", 51.5061, -0.3786),
    ("Hayes", 51.5031, -0.4207),
    ("Reading", 51.459, -0.9722),
    ("Didcot", 51.6111, -1.2425),
    ("Swindon", 51.5656, -1.7859),
    ("Chippenham", 51.4625, -2.1154),
    ("Bath", 51.3777, -2.357),
    ("Bristol Temple Meads", 51.4491, -2.5813),
    ("Avonmouth Freight Terminal", 51.5007, -2.6992),
    ("Filton", 51.508, -2.576),
    ("Patchway", 51.5259, -2.5627),
    ("Severn Tunnel Junction", 51.5848, -2.7772),
    ("Newport", 51.5888, -2.999),
    ("Cardiff", 51.476, -3.1791),
    ("Bridgend", 51.5069, -3.575),
    ("Port Talbot", 51.5917, -3.7811),
    ("Swansea Materials Terminal", 51.6251, -3.9416),
]
DUTIES = [
    ("LONDON-AVONMOUTH", 0, 9, [5]),
    ("AVONMOUTH-CARDIFF", 9, 14, [13]),
    ("CARDIFF-SWANSEA", 14, 17, [16]),
    ("LONDON-SWANSEA", 0, 17, [5, 9, 13, 14]),
]


def rebuild(source: Path, output: Path, download: bool):
    source.mkdir(parents=True, exist_ok=True)
    names = [f"NetworkLinks.{suffix}" for suffix in ("shp", "shx", "dbf", "prj")]
    for name in [*names, "AttributionTable.csv"]:
        if download:
            urllib.request.urlretrieve(BASE + "network-model/VectorLinks/" + name, source / name)
        if not (source / name).is_file():
            raise FileNotFoundError(f"Missing {name}; use --download or supply the pinned source.")
    # Verify source bytes against the reviewed fixture before rebuilding.
    reviewed = json.loads(output.read_text(encoding="utf-8"))["metadata"]
    for name, expected in reviewed["source_files"].items():
        local = source / name.replace("network-model_VectorLinks_", "")
        if hashlib.sha256(local.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Source checksum mismatch: {name}")
    graph = nx.Graph()
    reader = shapefile.Reader(str(source / "NetworkLinks.shp"))
    for item in reader.iterShapeRecords():
        shape = item.shape
        if (
            shape.bbox[2] < 240000
            or shape.bbox[0] > 530000
            or shape.bbox[3] < 150000
            or shape.bbox[1] > 230000
        ):
            continue
        if len(shape.parts) != 1:
            raise ValueError("Multipart geometry must be handled explicitly, never bridged.")
        for first, second in zip(shape.points, shape.points[1:], strict=False):
            a, b = (tuple(round(value, 1) for value in point) for point in (first, second))
            distance = math.dist(a, b)
            if distance:
                graph.add_edge(a, b, weight=distance, link=item.record["L_LINK_ID"])
    nodes = sorted(max(nx.connected_components(graph), key=len))
    tree = cKDTree(nodes)
    # Pin the same non-grid datum transform used for the reviewed fixture.
    # Auto-selected OSTN grids differ between machines and would change bytes.
    to_wgs = Transformer.from_pipeline(
        "+proj=pipeline +step +inv +proj=tmerc +lat_0=49 +lon_0=-2 "
        "+k=0.9996012717 +x_0=400000 +y_0=-100000 +ellps=airy "
        "+step +proj=push +v_3 +step +proj=cart +ellps=airy "
        "+step +proj=helmert +x=446.448 +y=-125.157 +z=542.06 "
        "+rx=0.15 +ry=0.247 +rz=0.842 +s=-20.489 +convention=position_vector "
        "+step +inv +proj=cart +ellps=WGS84 +step +proj=pop +v_3 "
        "+step +proj=unitconvert +xy_in=rad +xy_out=deg"
    )
    anchors = []
    for name, lat, lon in WAYPOINTS:
        distance, index = tree.query(to_wgs.transform(lon, lat, direction="INVERSE"))
        anchors.append(
            {
                "name": name,
                "original_latitude": lat,
                "original_longitude": lon,
                "snap_distance_metres": round(float(distance), 3),
                "node": nodes[index],
            }
        )
    coordinates, indices, links = [], [0], []
    for a, b in zip(anchors, anchors[1:], strict=False):
        path = nx.shortest_path(graph, a["node"], b["node"], weight="weight")
        coordinates.extend(path if not coordinates else path[1:])
        indices.append(len(coordinates) - 1)
        links.extend(graph.edges[u, v]["link"] for u, v in zip(path, path[1:], strict=False))
    statuses = {}
    with (source / "AttributionTable.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            statuses.setdefault(int(row["L_LINK_ID"]), set()).add(row["TRACK_STATUS"])
    if any(statuses.get(link) != {"IN USE"} for link in set(links)):
        raise ValueError("Chosen source links do not all have IN USE status in this snapshot.")
    lonlat = [
        [round(lon, 8), round(lat, 8)]
        for lon, lat in (to_wgs.transform(*point) for point in coordinates)
    ]
    features = []
    for name, start, end, stops in DUTIES:
        first, last = indices[start], indices[end]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "route_id": "FG-RTE-" + name,
                    "origin": anchors[start]["name"],
                    "destination": anchors[end]["name"],
                    "named_points": {
                        str(indices[i] - first): anchors[i]["name"] for i in range(start, end + 1)
                    },
                    "intermediate_stop_indices": [indices[i] - first for i in stops],
                    "source_link_ids": sorted(set(links[first:last])),
                },
                "geometry": {"type": "LineString", "coordinates": lonlat[first : last + 1]},
            }
        )
    metadata = dict(reviewed)
    metadata["anchors"] = [
        {k: v for k, v in a.items() if k != "node"}
        | {"latitude": lonlat[indices[i]][1], "longitude": lonlat[indices[i]][0]}
        for i, a in enumerate(anchors)
    ]
    result = {"type": "FeatureCollection", "metadata": metadata, "features": features}
    output.write_text(json.dumps(result, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Rebuilt {len(features)} routes; all {len(set(links))} selected links IN USE in source.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("data/rail-source"))
    parser.add_argument("--download", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "src/fleetguard/generator/data/uk_rail_routes.geojson",
    )
    args = parser.parse_args()
    rebuild(args.source_dir, args.output, args.download)


if __name__ == "__main__":
    main()
