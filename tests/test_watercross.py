import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from watercross import load_waterways

FIXTURE = str(Path(__file__).parent / "fixtures" / "basic.opl")


def test_load_keeps_only_linear_waterways():
    ws = load_waterways(FIXTURE)
    assert set(ws) == {1}
    assert ws[1].node_ids == (10, 11, 12)
    assert ws[1].coords[0] == (139.0, 35.0)
