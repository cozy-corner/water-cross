"""data/crossings.json から、交差点を分類ごとに色分けした地図(HTML)を作る。"""

import argparse
import json
from pathlib import Path

KINDS = [
    ("shared_node", "共有ノード", "#d9480f"),
    ("grade_tagged", "立体(記入あり)", "#1971c2"),
]

TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>水路の交差点マップ</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map { height: 100%; margin: 0; }
  body { font: 14px system-ui, sans-serif; }
  .panel { background: #fff; padding: 8px 12px; border-radius: 6px; box-shadow: 0 1px 4px #0004; line-height: 1.8; }
  .panel label { display: block; cursor: pointer; }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
  .popup td { padding: 1px 6px 1px 0; vertical-align: top; }
</style>
</head>
<body>
<div id="map"></div>
<script>
const KINDS = __KINDS__;
const ROWS = __ROWS__;

const map = L.map("map", { preferCanvas: true }).setView([36.2, 138.2], 6);
// OSM の公式タイルは file:// からの読み込みを拒否するので、地理院タイルを使う
L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank">地理院タイル</a> | 交差点データ &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const wayLine = (w) => {
  const attrs = ["tunnel", "bridge", "layer"].filter((k) => w[k] != null).map((k) => `${k}=${esc(w[k])}`);
  const label = esc(w.name || "(無名)");
  return `<a href="https://www.openstreetmap.org/way/${w.id}" target="_blank">${label}</a> (${[esc(w.waterway), ...attrs].join(", ")})`;
};

const groups = {};
for (const [kind, label, color] of KINDS) groups[kind] = { label, color, layer: L.layerGroup().addTo(map), n: 0 };

for (const r of ROWS) {
  const g = groups[r.kind];
  g.n++;
  const lat = r.lat.toFixed(5), lon = r.lon.toFixed(5);
  const node = r.node_id == null ? "" : `<a href="https://www.openstreetmap.org/node/${r.node_id}" target="_blank">node</a> `;
  const wayText = (w) => `${w.name || "(無名)"} (${[w.waterway, ...["tunnel", "bridge", "layer"].filter((k) => w[k] != null).map((k) => `${k}=${w[k]}`)].join(", ")}) https://www.openstreetmap.org/way/${w.id}`;
  const text = [
    `分類: ${g.label}`,
    `水路A: ${wayText(r.a)}`,
    `水路B: ${wayText(r.b)}`,
    `座標: ${lat}, ${lon}`,
    ...(r.node_id == null ? [] : [`node: https://www.openstreetmap.org/node/${r.node_id}`]),
  ].join("\\n");
  const html = `<button onclick="navigator.clipboard.writeText(this.dataset.text)" data-text="${esc(text)}">コピー</button>
  <table class="popup">
    <tr><td>分類</td><td>${g.label}</td></tr>
    <tr><td>水路A</td><td>${wayLine(r.a)}</td></tr>
    <tr><td>水路B</td><td>${wayLine(r.b)}</td></tr>
    <tr><td>座標</td><td>${lat}, ${lon}</td></tr>
    <tr><td>OSM</td><td>${node}<a href="https://www.openstreetmap.org/#map=19/${lat}/${lon}" target="_blank">map</a></td></tr>
    <tr><td>Google</td><td><a href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lon}" target="_blank">ストリートビュー</a></td></tr>
  </table>`;
  // 淡色地図の上で白く縁取り、背景に埋もれないようにする
  L.circleMarker([r.lat, r.lon], { radius: 8, color: "#fff", weight: 2, fillColor: g.color, fillOpacity: 0.95 })
    .bindPopup(html).addTo(g.layer);
}

const legend = L.control({ position: "topright" });
legend.onAdd = () => {
  const div = L.DomUtil.create("div", "panel");
  div.innerHTML = `<b>水路の交差点 ${ROWS.length.toLocaleString()} 件</b>` + KINDS.map(([kind, label, color]) =>
    `<label><input type="checkbox" data-kind="${kind}" checked> <span class="dot" style="background:${color}"></span>${label} ${groups[kind].n.toLocaleString()}</label>`
  ).join("");
  div.addEventListener("change", (e) => {
    const g = groups[e.target.dataset.kind];
    e.target.checked ? g.layer.addTo(map) : map.removeLayer(g.layer);
  });
  L.DomEvent.disableClickPropagation(div);
  return div;
};
legend.addTo(map);
</script>
</body>
</html>
"""


def _js(value) -> str:
    # 名前に "</script>" が入っていても script 要素を閉じさせない
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render_map(rows: list[dict]) -> str:
    return TEMPLATE.replace("__KINDS__", _js(KINDS)).replace("__ROWS__", _js(rows))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("out")
    args = ap.parse_args()
    rows = json.loads(Path(args.json).read_text())["crossings"]
    Path(args.out).write_text(render_map(rows))


if __name__ == "__main__":
    main()
