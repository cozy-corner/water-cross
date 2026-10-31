import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from watercross import (
    Waterway,
    geometric_crossings,
    load_waterways,
    node_flows,
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
SW, SE = (5, -0.001, -0.001), (6, 0.001, -0.001)
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


def test_shared_node_crossing_straight():
    [c] = shared_node_crossings(CROSS)
    assert c.kind == "shared_node" and c.straight is True
    assert (c.way_a, c.way_b, c.node_id) == (1, 2, 100)


def test_merge_then_split_not_straight():
    ws = ways(make(1, [W, C]), make(2, [SW, C]), make(3, [C, E]), make(4, [C, SE]))
    [c] = shared_node_crossings(ws)
    assert c.straight is False


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
