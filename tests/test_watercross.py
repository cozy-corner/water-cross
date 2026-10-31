import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from watercross import (
    Crossing,
    Waterway,
    dedupe,
    geometric_crossings,
    load_waterways,
    node_flows,
    render_markdown,
    to_row,
    shared_node_crossings,
)

FIXTURE = str(Path(__file__).parent / "fixtures" / "basic.opl")


def test_load_keeps_only_linear_waterways():
    ws = load_waterways(FIXTURE)
    assert set(ws) == {1}
    assert ws[1].node_ids == (10, 11, 12)
    assert ws[1].coords[0] == (139.0, 35.0)


def make(wid, pts, tags=None):
    """pts: [(node_id, lon, lat), ...] を流下方向の順に"""
    return Waterway(
        id=wid,
        tags=tags or {"waterway": "drain"},
        node_ids=tuple(p[0] for p in pts),
        coords=tuple((p[1], p[2]) for p in pts),
    )


def ways(*ws):
    return {w.id: w for w in ws}


W, E, N, S = (1, -0.001, 0), (2, 0.001, 0), (3, 0, 0.001), (4, 0, -0.001)
C = (100, 0, 0)

CROSS = ways(make(1, [W, C, E]), make(2, [N, C, S]))


def test_flows_cross():
    assert node_flows(CROSS)[100] == (2, 2)


def test_flows_merge():
    ws = ways(make(1, [W, C]), make(2, [N, C]), make(3, [C, E]))
    assert node_flows(ws)[100] == (2, 1)


def test_flows_split():
    ws = ways(make(1, [W, C]), make(2, [C, E]), make(3, [C, S]))
    assert node_flows(ws)[100] == (1, 2)


def test_closed_way_endpoint_counts_as_pass_through():
    ws = ways(make(1, [C, (7, 0.001, 0.001), N, C]), make(2, [W, C, E]))
    assert node_flows(ws)[100] == (2, 2)


def test_shared_node_crossing():
    [c] = shared_node_crossings(CROSS)
    assert c.kind == "shared_node"
    assert (c.way_a, c.way_b, c.node_id) == (1, 2, 100)


def test_merge_is_not_crossing():
    ws = ways(make(1, [W, C]), make(2, [N, C]), make(3, [C, E]))
    assert shared_node_crossings(ws) == []


def test_tunnel_crossing_is_grade_tagged():
    ws = ways(make(1, [W, E]), make(2, [N, S], {"waterway": "canal", "tunnel": "culvert"}))
    cs, _ = geometric_crossings(ws)
    assert [c.kind for c in cs] == ["grade_tagged"] and cs[0].node_id is None
    assert (cs[0].lon, cs[0].lat) == (0, 0)


def test_layer_difference_is_grade_tagged():
    ws = ways(make(1, [W, E]), make(2, [N, S], {"waterway": "canal", "layer": "-1"}))
    cs, _ = geometric_crossings(ws)
    assert [c.kind for c in cs] == ["grade_tagged"]


def test_untagged_crossing():
    cs, _ = geometric_crossings(ways(make(1, [W, E]), make(2, [N, S])))
    assert [c.kind for c in cs] == ["grade_untagged"]


def test_shared_node_not_reported_here():
    assert geometric_crossings(CROSS)[0] == []


def test_endpoint_on_line_is_touch_not_crossing():
    cs, stats = geometric_crossings(ways(make(1, [W, E]), make(2, [N, (101, 0, 0)])))
    assert cs == [] and stats["endpoint_touch"] == 1


def test_overlap_counted_not_reported():
    cs, stats = geometric_crossings(ways(make(1, [W, E]), make(2, [(11, -0.001, 0), (12, 0.001, 0)])))
    assert cs == [] and stats["overlap"] == 1


def test_two_crossings_same_pair():
    b = make(2, [(11, -0.0005, 0.001), (12, -0.0005, -0.001), (13, 0.0005, -0.001), (14, 0.0005, 0.001)])
    assert len(geometric_crossings(ways(make(1, [W, E]), b))[0]) == 2


def test_dedupe_same_crossing_from_two_regions():
    c = Crossing("grade_tagged", 60964194, 1117757672, 139.38766, 35.72734, None)
    assert len(dedupe([c, replace(c)])) == 1


def test_dedupe_keeps_distinct_points_of_same_pair():
    c = Crossing("grade_untagged", 1, 2, 139.0, 35.0, None)
    assert len(dedupe([c, replace(c, lon=139.001)])) == 2


def test_markdown_has_links_and_pair_summary():
    a = make(60964194, [(1, 139.3876, 35.7273), (2, 139.3878, 35.7274)],
             {"waterway": "canal", "name": "玉川上水", "tunnel": "yes", "layer": "-1"})
    b = make(1117757672, [(3, 139.3877, 35.7275), (4, 139.3877, 35.7272)],
             {"waterway": "river", "name": "残堀川"})
    c = Crossing("grade_tagged", 60964194, 1117757672, 139.38766, 35.72734, None)
    md = render_markdown([to_row(c, ways(a, b), "kanto")], {"overlap": 0, "endpoint_touch": 0})
    assert "https://www.openstreetmap.org/way/60964194" in md
    assert "#map=19/35.72734/139.38766" in md
    assert "canal × river" in md
    assert "玉川上水" in md


def test_shared_node_crossing_reports_two_flows_when_ways_split_at_node():
    # 両方の水路が交点で way に分かれている。同じ流れの上下流(1 と 4)を組にしない
    ws = ways(make(1, [W, C]), make(2, [N, C]), make(3, [C, S]), make(4, [C, E]))
    [c] = shared_node_crossings(ws)
    assert (c.way_a, c.way_b) == (1, 2)
