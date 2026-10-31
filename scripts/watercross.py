"""OSM の水路どうしの交差点を検出する。"""

from dataclasses import dataclass

import osmium

WATERWAY_TYPES = frozenset({"river", "stream", "canal", "drain", "ditch", "tidal_channel"})


@dataclass(frozen=True)
class Waterway:
    id: int
    tags: dict[str, str]
    node_ids: tuple[int, ...]
    coords: tuple[tuple[float, float], ...]  # (lon, lat)


def load_waterways(path: str) -> dict[int, Waterway]:
    ways: dict[int, Waterway] = {}
    fp = osmium.FileProcessor(path, osmium.osm.NODE | osmium.osm.WAY).with_locations()
    for w in fp:
        if not w.is_way() or w.tags.get("waterway") not in WATERWAY_TYPES:
            continue
        # 切り出し境界で座標が欠けたノードは捨てる
        nodes = [(n.ref, (n.lon, n.lat)) for n in w.nodes if n.location.valid()]
        if len(nodes) < 2:
            continue
        ways[w.id] = Waterway(
            id=w.id,
            tags={t.k: t.v for t in w.tags},
            node_ids=tuple(r for r, _ in nodes),
            coords=tuple(c for _, c in nodes),
        )
    return ways
