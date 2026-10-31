import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from watercross import Waterway, load_waterways, node_flows, shared_node_crossings

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
