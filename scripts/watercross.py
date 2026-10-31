"""OSM の水路どうしの交差点を検出する。"""

import math
from dataclasses import dataclass
from itertools import permutations

import osmium
import shapely
from shapely import LineString

WATERWAY_TYPES = frozenset({"river", "stream", "canal", "drain", "ditch", "tidal_channel"})
STRAIGHT_TOLERANCE_DEG = 35  # 153号調査の貫通軸と同じ許容


@dataclass(frozen=True)
class Waterway:
    id: int
    tags: dict[str, str]
    node_ids: tuple[int, ...]
    coords: tuple[tuple[float, float], ...]  # (lon, lat)


@dataclass
class Crossing:
    kind: str  # shared_node / grade_tagged / grade_untagged
    way_a: int
    way_b: int
    lon: float
    lat: float
    node_id: int | None
    straight: bool | None


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


def _bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = (b[0] - a[0]) * math.cos(math.radians((a[1] + b[1]) / 2))
    dy = b[1] - a[1]
    return math.degrees(math.atan2(dx, dy)) % 360


def _angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _node_arms(ways: dict[int, Waterway]):
    """ノードID → (way ID の集合, 入る線の進行方位, 出る線の進行方位)。

    OSM の水路は流下方向に描くので、way の終点は入る線、始点は出る線、途中の点は入1出1。
    """
    arms: dict[int, tuple[set[int], list[float], list[float]]] = {}
    for w in ways.values():
        ids, cs = w.node_ids, w.coords
        closed = len(ids) > 2 and ids[0] == ids[-1]
        last = len(ids) - 1
        for i, nid in enumerate(ids):
            if closed and i == last:
                continue  # 始点と同じ点。始点側で通過1回として数える
            ws_, ins, outs = arms.setdefault(nid, (set(), [], []))
            ws_.add(w.id)
            prev = i - 1 if i > 0 else (last - 1 if closed else None)
            nxt = i + 1 if i < last else None
            if prev is not None:
                ins.append(_bearing(cs[prev], cs[i]))
            if nxt is not None:
                outs.append(_bearing(cs[i], cs[nxt]))
    return {n: a for n, a in arms.items() if len(a[0]) >= 2}


def node_flows(ways: dict[int, Waterway]) -> dict[int, tuple[int, int]]:
    return {n: (len(ins), len(outs)) for n, (_, ins, outs) in _node_arms(ways).items()}


def _is_straight(ins: list[float], outs: list[float]) -> bool:
    # 入ってきた線それぞれが、進行方向を保ったまま別々の出る線へ抜けているか
    return any(
        all(_angle_diff(i, o) <= STRAIGHT_TOLERANCE_DEG for i, o in zip(ins, perm))
        for perm in permutations(outs)
    )


def shared_node_crossings(ways: dict[int, Waterway]) -> list[Crossing]:
    result = []
    for nid, (wids, ins, outs) in _node_arms(ways).items():
        if len(ins) != 2 or len(outs) != 2:
            continue
        w = ways[min(wids)]
        lon, lat = w.coords[w.node_ids.index(nid)]
        result.append(
            Crossing("shared_node", min(wids), max(wids), lon, lat, nid, _is_straight(ins, outs))
        )
    return result


def _key(c: tuple[float, float]) -> tuple[float, float]:
    return (round(c[0], 9), round(c[1], 9))


def _ends(w: Waterway) -> set[tuple[float, float]]:
    if w.node_ids[0] == w.node_ids[-1]:
        return set()
    return {_key(w.coords[0]), _key(w.coords[-1])}


def _active(v: str | None) -> bool:
    return v is not None and v != "no"


def _is_grade_separated(a: Waterway, b: Waterway) -> bool:
    if any(_active(w.tags.get(k)) for w in (a, b) for k in ("tunnel", "bridge")):
        return True
    return a.tags.get("layer", "0").strip() != b.tags.get("layer", "0").strip()


def geometric_crossings(ways: dict[int, Waterway]) -> tuple[list[Crossing], dict[str, int]]:
    """ノードを共有せずに線が交わる点。共有ノードでの交差は shared_node_crossings の担当。"""
    wl = list(ways.values())
    lines = [LineString(w.coords) for w in wl]
    tree = shapely.STRtree(lines)
    left, right = tree.query(lines, predicate="intersects")
    stats = {"overlap": 0, "endpoint_touch": 0}
    result = []
    for i, j in zip(left, right):
        if i >= j:
            continue
        a, b = wl[i], wl[j]
        parts = shapely.get_parts(lines[i].intersection(lines[j]))
        if any(p.geom_type != "Point" for p in parts):
            stats["overlap"] += 1
            continue
        a_nodes = dict(zip(a.node_ids, a.coords))
        shared = {_key(a_nodes[n]) for n in set(a.node_ids) & set(b.node_ids)}
        ends = _ends(a) | _ends(b)
        for p in parts:
            k = _key((p.x, p.y))
            if k in shared:
                continue
            if k in ends:
                stats["endpoint_touch"] += 1
                continue
            kind = "grade_tagged" if _is_grade_separated(a, b) else "grade_untagged"
            lo, hi = sorted((a.id, b.id))
            result.append(Crossing(kind, lo, hi, p.x, p.y, None, None))
    return result, stats
