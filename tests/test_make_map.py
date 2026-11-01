import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from make_map import render_map

ROW = {
    "kind": "grade_tagged", "region": "kanto", "lat": 35.72734, "lon": 139.38766, "node_id": None,
    "a": {"id": 60964194, "name": "玉川上水", "waterway": "canal", "tunnel": "yes", "bridge": None, "layer": "-1"},
    "b": {"id": 1117757672, "name": "残堀川", "waterway": "river", "tunnel": None, "bridge": None, "layer": None},
}


def test_map_embeds_rows_and_legend():
    html = render_map([ROW])
    assert "玉川上水" in html and "60964194" in html
    for label in ("共有ノード", "立体(記入あり)"):
        assert label in html


def test_map_escapes_script_close_in_names():
    row = {**ROW, "a": {**ROW["a"], "name": "</script><b>"}}
    assert "</script><b>" not in render_map([row])


def test_map_has_street_view_link():
    assert "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=" in render_map([ROW])
