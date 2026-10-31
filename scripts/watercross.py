"""OSM の水路どうしの交差点を検出する。"""

import argparse
import json
from collections import Counter
from pathlib import Path
from dataclasses import dataclass

import osmium
import shapely
from shapely import LineString

# ditch は道路脇の側溝や田の縁の溝。道路と水路の交差が水路どうしの交差として出るので対象外
WATERWAY_TYPES = frozenset({"river", "stream", "canal", "drain", "tidal_channel"})


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


def _node_arms(ways: dict[int, Waterway]):
    """ノードID → (way ID の集合, 入る線の way ID, 出る線の way ID)。

    OSM の水路は流下方向に描くので、way の終点は入る線、始点は出る線、途中の点は入1出1。
    """
    arms: dict[int, tuple[set[int], list[int], list[int]]] = {}
    for w in ways.values():
        ids = w.node_ids
        closed = len(ids) > 2 and ids[0] == ids[-1]
        last = len(ids) - 1
        for i, nid in enumerate(ids):
            if closed and i == last:
                continue  # 始点と同じ点。始点側で通過1回として数える
            ws_, ins, outs = arms.setdefault(nid, (set(), [], []))
            ws_.add(w.id)
            if i > 0 or closed:
                ins.append(w.id)
            if i < last:
                outs.append(w.id)
    return {n: a for n, a in arms.items() if len(a[0]) >= 2}


def node_flows(ways: dict[int, Waterway]) -> dict[int, tuple[int, int]]:
    return {n: (len(ins), len(outs)) for n, (_, ins, outs) in _node_arms(ways).items()}


def shared_node_crossings(ways: dict[int, Waterway]) -> list[Crossing]:
    result = []
    for nid, (wids, ins, outs) in _node_arms(ways).items():
        if len(ins) != 2 or len(outs) != 2:
            continue
        # 入る線は2本とも別の流れなので、それを交差の2本とする。
        # way ID の最小/最大だと、交点で分かれた同じ流れの上流と下流を組にしてしまう
        a, b = sorted(ins)
        lon, lat = ways[a].coords[ways[a].node_ids.index(nid)]
        result.append(Crossing("shared_node", a, b, lon, lat, nid))
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
            result.append(Crossing(kind, lo, hi, p.x, p.y, None))
    return result, stats


KIND_ORDER = ("shared_node", "grade_tagged", "grade_untagged")
KIND_LABEL = {
    "shared_node": "共有ノード",
    "grade_tagged": "立体(記入あり)",
    "grade_untagged": "立体(記入なし)",
}


def _crossing_key(c: Crossing):
    if c.node_id is not None:
        return ("n", c.node_id)
    return ("p", c.way_a, c.way_b, round(c.lon, 6), round(c.lat, 6))


def dedupe(crossings: list[Crossing]) -> list[Crossing]:
    """地方の切り出しが重なる境界で、同じ交差が2回出るのを1件にする。"""
    seen = {}
    for c in crossings:
        seen.setdefault(_crossing_key(c), c)
    return list(seen.values())


def _way_info(w: Waterway) -> dict:
    return {"id": w.id, **{k: w.tags.get(k) for k in ("name", "waterway", "tunnel", "bridge", "layer")}}


def to_row(c: Crossing, ways: dict[int, Waterway], region: str) -> dict:
    return {
        "kind": c.kind,
        "region": region,
        "lat": c.lat,
        "lon": c.lon,
        "node_id": c.node_id,
        "a": _way_info(ways[c.way_a]),
        "b": _way_info(ways[c.way_b]),
    }


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _way_cell(w: dict) -> str:
    extra = [f"{k}={w[k]}" for k in ("tunnel", "bridge", "layer") if w[k] is not None]
    label = _cell(w["name"] or "(無名)")
    attrs = ", ".join([w["waterway"], *extra])
    return f"[{label}](https://www.openstreetmap.org/way/{w['id']}) ({_cell(attrs)})"


def _pair(r: dict) -> str:
    return " × ".join(sorted((r["a"]["waterway"], r["b"]["waterway"])))


def render_markdown(rows: list[dict], stats: dict) -> str:
    rows = sorted(rows, key=lambda r: (KIND_ORDER.index(r["kind"]), r["region"], r["lat"]))
    out = ["# 水路の交差点", "", "## 分類別", "", "| 分類 | 件数 |", "|---|---|"]
    kinds = Counter(r["kind"] for r in rows)
    out += [f"| {KIND_LABEL[k]} | {kinds[k]} |" for k in KIND_ORDER]
    out += ["", "## 水路の種類の組み合わせ別", "", "| 組み合わせ | 件数 |", "|---|---|"]
    out += [f"| {p} | {n} |" for p, n in Counter(_pair(r) for r in rows).most_common()]
    out += [
        "",
        "## 交差に数えなかったもの",
        "",
        f"- 線どうしが重なっている組: {stats['overlap']}",
        f"- 端点が他の線に乗っているがノード未接続: {stats['endpoint_touch']}",
        "",
        "## 一覧",
        "",
        "| # | 分類 | 水路A | 水路B | 座標 | 地方 | OSM |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        lat, lon = f"{r['lat']:.5f}", f"{r['lon']:.5f}"
        links = f"[map](https://www.openstreetmap.org/#map=19/{lat}/{lon})"
        if r["node_id"] is not None:
            links = f"[node](https://www.openstreetmap.org/node/{r['node_id']}) " + links
        out.append(
            f"| {i} | {KIND_LABEL[r['kind']]} | {_way_cell(r['a'])} | {_way_cell(r['b'])} "
            f"| {lat}, {lon} | {r['region']} | {links} |"
        )
    return "\n".join(out) + "\n"


def report(paths: list[str], json_out: str, md_out: str) -> None:
    rows, seen = [], set()
    stats = {"overlap": 0, "endpoint_touch": 0}
    for path in paths:
        region = Path(path).name.split("_")[0].split("-")[0]
        ways = load_waterways(path)
        geo, st = geometric_crossings(ways)
        for k in stats:
            stats[k] += st[k]
        for c in shared_node_crossings(ways) + geo:
            key = _crossing_key(c)
            if key in seen:
                continue
            seen.add(key)
            rows.append(to_row(c, ways, region))
        print(f"{region}: {len(ways)} ways, 累計 {len(rows)} 件")
    Path(json_out).write_text(json.dumps({"stats": stats, "crossings": rows}, ensure_ascii=False, indent=1))
    Path(md_out).write_text(render_markdown(rows, stats))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("pbf", nargs="+")
    r.add_argument("--json", required=True)
    r.add_argument("--md", required=True)
    args = ap.parse_args()
    report(args.pbf, args.json, args.md)


if __name__ == "__main__":
    main()
