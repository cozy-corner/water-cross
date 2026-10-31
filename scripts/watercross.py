"""OSM の水路どうしの交差点を検出する。"""

import math
from dataclasses import dataclass
from itertools import permutations

import osmium

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
