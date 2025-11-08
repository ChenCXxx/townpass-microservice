from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy import create_engine, text

# When this script is executed directly (python scripts/load_road_segments.py)
# the package root (backend/) may not be on sys.path. Ensure the project
# root is first on sys.path so `from app.config import settings` resolves.
import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import settings


def normalize_osmid(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)


def parse_oneway(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "t", "1", "yes", "y"}:
            return True
        if lowered in {"false", "f", "0", "no", "n"}:
            return False
    return None


def parse_length(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _canonicalize_linestring(coords: List[Any]) -> Tuple[Tuple[float, ...], ...]:
    """Return a canonical tuple representation of a LineString's coordinates."""
    seq = tuple(tuple(map(float, point[:2])) for point in coords)
    rev = tuple(reversed(seq))
    return seq if seq <= rev else rev


def load_rows(file_path: Path) -> list[dict[str, Any]]:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    grouped: Dict[str, Dict[str, Any]] = {}

    for feature in data.get("features", []):
        geometry = feature.get("geometry")
        if not geometry or geometry.get("type") != "LineString":
            continue

        coords = geometry.get("coordinates")
        if not coords or len(coords) < 2:
            continue

        properties = feature.get("properties") or {}
        osmid = normalize_osmid(properties.get("osmid"))
        if not osmid:
            continue

        canonical = _canonicalize_linestring(coords)
        entry = grouped.setdefault(
            osmid,
            {
                "name": None,
                "highway": None,
                "lanes": None,
                "oneway": None,
                "length_m": 0.0,
                "segments": [],
                "segment_keys": set(),
                "segment_properties": [],
                "base_properties": None,
            },
        )

        if canonical in entry["segment_keys"]:
            continue

        entry["segment_keys"].add(canonical)
        entry["segments"].append(coords)
        entry["segment_properties"].append(properties)

        if entry["base_properties"] is None:
            entry["base_properties"] = dict(properties)

        entry["name"] = entry["name"] or properties.get("name")
        entry["highway"] = entry["highway"] or properties.get("highway")
        entry["lanes"] = entry["lanes"] or properties.get("lanes")

        oneway_parsed = parse_oneway(properties.get("oneway"))
        if entry["oneway"] is None and oneway_parsed is not None:
            entry["oneway"] = oneway_parsed

        length_val = parse_length(properties.get("length")) or parse_length(properties.get("length_m"))
        if length_val:
            entry["length_m"] += length_val

    rows: list[dict[str, Any]] = []
    for osmid, entry in grouped.items():
        if not entry["segments"]:
            continue

        geometry: Dict[str, Any]
        if len(entry["segments"]) == 1:
            geometry = {"type": "LineString", "coordinates": entry["segments"][0]}
        else:
            geometry = {"type": "MultiLineString", "coordinates": entry["segments"]}

        properties: Dict[str, Any] = entry["base_properties"] or {}
        properties = dict(properties)  # shallow copy to avoid mutating source data
        properties.update(
            {
                "segment_count": len(entry["segments"]),
                "segments": entry["segment_properties"],
            }
        )

        rows.append(
            {
                "osmid": osmid,
                "name": entry["name"],
                "highway": entry["highway"],
                "lanes": entry["lanes"],
                "oneway": entry["oneway"],
                "length_m": entry["length_m"] or None,
                "properties": json.dumps(properties, ensure_ascii=False),
                "geometry": json.dumps(geometry, ensure_ascii=False),
            }
        )

    return rows


def ingest(file_path: Path) -> int:
    rows = load_rows(file_path)
    if not rows:
        return 0

    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    insert_sql = text(
        """
        INSERT INTO road_segments
            (osmid, name, highway, lanes, oneway, length_m, properties, geometry)
        VALUES
            (:osmid, :name, :highway, :lanes, :oneway, :length_m,
             CAST(:properties AS JSONB), CAST(:geometry AS JSONB));
        """
    )

    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE road_segments RESTART IDENTITY CASCADE"))
        for row in rows:
            connection.execute(insert_sql, row)

    engine.dispose()
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load road GeoJSON into Postgres")
    parser.add_argument(
        "geojson",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parents[1] / "data" / "TaipeiRoadCenterLine.geojson",
        help="Path to the GeoJSON file (default: data/TaipeiRoadCenterLine.geojson)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    file_path: Path = args.geojson.resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"GeoJSON file not found: {file_path}")

    inserted = ingest(file_path)
    print(f"Processed {inserted} road segments from {file_path}")


if __name__ == "__main__":
    main()
