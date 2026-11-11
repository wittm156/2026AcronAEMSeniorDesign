"""Reads airports directly from the simulator's existing OpenStreetMap export
which is located in "ui" / "SyntheticVision" / "airports_save.json
If not in the database an error is raised
"""
import json
from math import isfinite
from pathlib import Path

AIRPORTS_PATH = Path(__file__).resolve().parents[1] / "ui" / "SyntheticVision" / "airports_save.json"


def load_database(path=None, origin="KLVN"):
    source = Path(path) if path is not None else AIRPORTS_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    airports = []
    ids = set()
    for element in data["elements"]:
        tags = element.get("tags", {})
        if tags.get("aeroway") != "aerodrome":
            continue
        position = element if element.get("type") == "node" else element.get("center", {})
        lat = position.get("lat")
        lon = position.get("lon")
        if lat is None or lon is None:
            continue
        lat = float(lat)
        lon = float(lon)
        if not (isfinite(lat) and isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"Invalid coordinates for airport {element['id']}.")
        airport_id = (tags.get("icao") or tags.get("faa") or tags.get("iata")
                      or f"OSM-{element['type']}-{element['id']}").upper()
        if airport_id in ids:
            raise ValueError(f"Duplicate airport ID: {airport_id}.")
        ids.add(airport_id)
        aliases = set()
        for key in ("icao", "faa", "iata", "alt_name", "short_name", "official_name", "name:en", "city_served"):
            aliases.update(value.strip() for value in tags.get(key, "").split(";") if value.strip())
        airports.append({"id": airport_id, "name": tags.get("name", airport_id),
                         "aliases": sorted(aliases), "lat": lat, "lon": lon})
    if origin not in ids:
        raise ValueError(f"Origin {origin} is not in the airport database.")
    return {"origin": origin, "airports": airports, "waypoints": [], "routes": []}
