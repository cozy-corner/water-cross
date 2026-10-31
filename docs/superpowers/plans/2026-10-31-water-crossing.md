# 水路の交差点 検出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OSM の Geofabrik 日本8地方データから、水路どうしの交差点(立体・平面)を列挙し、表と OSM リンクで出す。

**Architecture:** `osmium tags-filter` で waterway に絞った PBF を pyosmium で読み、way ごとに LineString を作る。共有ノードは入る線/出る線の数で、非共有の交差は shapely STRtree で拾う。結果を JSON と Markdown にする。スクリプトは `scripts/watercross.py` の1本。

**Tech Stack:** Python 3.12+, uv, pyosmium, shapely 2, pytest, osmium-tool (CLI)

**Spec:** `docs/superpowers/specs/2026-10-31-water-crossing-design.md`

## Global Constraints

- 対象: `waterway` ∈ {`river`, `stream`, `canal`, `drain`, `ditch`, `tidal_channel`} の way だけ
- 入力: `~/y-junctions-data/osm/{hokkaido,tohoku,kanto,chubu,kansai,chugoku,shikoku,kyushu}-latest.osm.pbf`
- 流下方向: way の始点=出る、終点=入る、途中の点=入1出1(OSM の waterway は流下方向に描く決まり)
- 関門: 関東で way 60964194(玉川上水, `tunnel=yes`, `layer=-1`)× way 1117757672(残堀川)の交差が `grade_tagged` で出る
- 依存は uv(`pyproject.toml`)。中間 PBF は `data/` に置き、元データは置かない

## Review Focus

1. **端点が他の線の上に乗っているがノード未接続**(つなぎ忘れの合流)→ 交差に数えず `endpoint_touch` 件数に入れる。Task 3 でテスト
2. **同じ2本が複数回交わる**(蛇行)→ 交点ごとに別の行。Task 3 でテスト
3. **始点=終点の閉じた way**(環状の水路)→ その点は入1出1として数え、例外にしない。Task 2 でテスト
4. **ノード座標が欠けた way**(切り出し境界)→ 2点未満なら読み飛ばし、落ちない。Task 1 でテスト
5. **地方の境界で同じ交差が2地方に出る**→ 1件にまとめる。Task 4 でテスト

---

### Task 1: 環境と読み込み

**Files:**
- Create: `pyproject.toml`, `scripts/watercross.py`, `tests/test_watercross.py`, `tests/fixtures/basic.opl`

**Interfaces:**
- Produces:
  - `WATERWAY_TYPES: frozenset[str]`
  - `@dataclass(frozen=True) class Waterway: id: int; tags: dict[str, str]; node_ids: tuple[int, ...]; coords: tuple[tuple[float, float], ...]`(coords は (lon, lat))
  - `load_waterways(path: str) -> dict[int, Waterway]`

- [ ] **Step 1:** `uv init --bare` 後 `uv add pyosmium shapely` / `uv add --dev pytest`
- [ ] **Step 2: テストを書く** — `tests/fixtures/basic.opl` に、river 1本(3ノード)、`waterway=riverbank` 1本、`highway=residential` 1本、座標なしノードを含む stream 1本(解決できるノードが1つだけ)を置く

```python
def test_load_keeps_only_linear_waterways():
    ws = load_waterways(FIXTURE)
    assert set(ws) == {1}            # riverbank, highway, 1点しかない stream は落ちる
    assert ws[1].node_ids == (10, 11, 12)
    assert ws[1].coords[0] == (139.0, 35.0)
```

- [ ] **Step 3:** `uv run pytest -k load` → FAIL(未定義)
- [ ] **Step 4:** 実装。`osmium.FileProcessor(path).with_locations()` で way を読み、`WATERWAY_TYPES` に入るものだけ、座標が解決できたノードが2つ以上のものだけ残す
- [ ] **Step 5:** `uv run pytest -k load` → PASS

### Task 2: 共有ノードの分類

**Files:**
- Modify: `scripts/watercross.py`, `tests/test_watercross.py`

**Interfaces:**
- Consumes: `Waterway`
- Produces:
  - `@dataclass class Crossing: kind: str; way_a: int; way_b: int; lon: float; lat: float; node_id: int | None`
  - `kind` ∈ {`shared_node`, `grade_tagged`, `grade_untagged`}
  - `node_flows(ways: dict[int, Waterway]) -> dict[int, tuple[int, int]]`(ノードID → (入る数, 出る数)。2本以上の way が通るノードだけ)
  - `shared_node_crossings(ways: dict[int, Waterway]) -> list[Crossing]`(入2出2のみ。way_a/way_b は関わる way の最小/最大 ID)

- [ ] **Step 1: テストを書く**(座標を手で置いた Waterway を直接作る)

```python
def test_flows_cross():      # A: 西→東に通過、B: 北→南に通過
    assert node_flows(ws)[100] == (2, 2)
def test_flows_merge():      # A, B が 100 で終わり C が 100 から始まる
    assert node_flows(ws)[100] == (2, 1)
def test_flows_split():      # A が 100 で終わり B, C が始まる
    assert node_flows(ws)[100] == (1, 2)
def test_closed_way_endpoint_counts_as_pass_through():  # 閉じた way + 通過する way
    assert node_flows(ws)[100] == (2, 2)
def test_shared_node_crossing():
    [c] = shared_node_crossings(cross_ws)
    assert c.kind == "shared_node"
def test_merge_is_not_crossing():
    assert shared_node_crossings(merge_ws) == []
```

- [ ] **Step 2:** `uv run pytest` → 新規テストが FAIL
- [ ] **Step 3:** 実装。閉じた way の始点=終点は1回の通過(入1出1)として数える
- [ ] **Step 4:** `uv run pytest` → PASS

### Task 3: ノードを共有しない交差

**Files:**
- Modify: `scripts/watercross.py`, `tests/test_watercross.py`

**Interfaces:**
- Consumes: `Waterway`, `Crossing`
- Produces: `geometric_crossings(ways: dict[int, Waterway]) -> tuple[list[Crossing], dict[str, int]]`(dict は `{"overlap": n, "endpoint_touch": n}`)

- [ ] **Step 1: テストを書く**

```python
def test_tunnel_crossing_is_grade_tagged():   # 十字、一方に tunnel=culvert
    cs, _ = geometric_crossings(ws)
    assert [c.kind for c in cs] == ["grade_tagged"] and cs[0].node_id is None
def test_layer_difference_is_grade_tagged():  # 一方に layer=-1、tunnel なし
def test_untagged_crossing():                 # タグなしの十字
    assert cs[0].kind == "grade_untagged"
def test_shared_node_not_reported_here():     # 交点にノードがあり両方の way が共有
    assert geometric_crossings(ws)[0] == []
def test_endpoint_on_line_is_touch_not_crossing():   # B の終点が A の線分の途中に乗る
    cs, stats = geometric_crossings(ws)
    assert cs == [] and stats["endpoint_touch"] == 1
def test_overlap_counted_not_reported():      # 同じ座標列の2本
    cs, stats = geometric_crossings(ws)
    assert cs == [] and stats["overlap"] == 1
def test_two_crossings_same_pair():           # B が A を2回またぐ
    assert len(geometric_crossings(ws)[0]) == 2
```

- [ ] **Step 2:** `uv run pytest` → 新規テストが FAIL
- [ ] **Step 3:** 実装。`shapely.STRtree(lines).query(lines, predicate="intersects")` で組を取り、`i < j` のみ。交差結果を点に分解し(`LineString` 成分があれば overlap に数えて点は捨てる)、次の点を除く: 両 way が共有するノードの座標と一致する点(Task 2 の担当)、どちらかの way の端点と一致する点(endpoint_touch に数える)。残った点は、`tunnel`(no 以外)/`bridge`(no 以外)のどちらかがある、または `layer` の値(なしは 0)が違えば `grade_tagged`、そうでなければ `grade_untagged`
- [ ] **Step 4:** `uv run pytest` → PASS

### Task 4: 出力と CLI

**Files:**
- Modify: `scripts/watercross.py`, `tests/test_watercross.py`

**Interfaces:**
- Consumes: Task 1〜3 の関数
- Produces:
  - `dedupe(crossings: list[Crossing]) -> list[Crossing]`(キー: `node_id` があればそれ、なければ `(way_a, way_b, round(lon, 6), round(lat, 6))`)
  - `render_markdown(rows: list[dict], stats: dict) -> str`
  - CLI: `uv run scripts/watercross.py report <filtered.pbf>... --json <out.json> --md <out.md>`(各 PBF に地方名=ファイル名先頭を付ける)

- [ ] **Step 1: テストを書く**

```python
def test_dedupe_same_crossing_from_two_regions():
    assert len(dedupe([c, replace(c)])) == 1
def test_markdown_has_links_and_pair_summary():
    md = render_markdown(rows, stats)
    assert "https://www.openstreetmap.org/way/60964194" in md
    assert "#map=19/35.72734/139.38766" in md
    assert "canal × river" in md      # waterway の組み合わせ別件数(名前順に並べた組)
```

- [ ] **Step 2:** `uv run pytest` → FAIL
- [ ] **Step 3:** 実装。行の列は spec の「表の列」の通り(#, 分類, 水路A/B の name・waterway・tunnel/bridge/layer, 座標, 地方, OSM リンク)。表の前に、分類別の件数、組み合わせ別の件数、overlap・endpoint_touch の件数を置く。並びは、分類(shared_node → grade_tagged → grade_untagged)、地方、緯度の順
- [ ] **Step 4:** `uv run pytest` → PASS

### Task 5: 実データで実行

**Files:**
- Create: `data/*_waterway.osm.pbf`(生成物)、`data/crossings.json`、`CROSSINGS.md`、`README.md`

- [ ] **Step 1: 関東で絞り込み**

```bash
osmium tags-filter ~/y-junctions-data/osm/kanto-latest.osm.pbf w/waterway -o data/kanto_waterway.osm.pbf --overwrite
uv run scripts/watercross.py report data/kanto_waterway.osm.pbf --json /tmp/kanto.json --md /tmp/kanto.md
```

- [ ] **Step 2: 関門** — `/tmp/kanto.json` に way 60964194 と 1117757672 の組の `grade_tagged` があること。なければ原因を調べてから先へ進む(実装を直すか、該当の way 構成を確認する)
- [ ] **Step 3:** 8地方すべてで Step 1 を実行し、まとめて `report` → `data/crossings.json`、`CROSSINGS.md`
- [ ] **Step 4:** `README.md` に、目的、再現コマンド、結果の要約(分類別・組み合わせ別の件数。river × river の件数で「自然の川は交差しない」仮説を確かめた結果)を書く。最後に OSM データの日付を書く(`osmium fileinfo` の `osmosis_replication_timestamp` など)
