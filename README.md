# 水路の交差点

玉川上水と残堀川のような「水路どうしの交差」を、OpenStreetMap から日本全国で探した記録。
`../route153-investigation`(同じ番号の道の自己交差)の続き。趣味。

## 判定

線の水路 `waterway=river|stream|canal|drain|ditch|tidal_channel` の、別々の2本が交わる点を拾い、
次の3つを交差に数える。合流・分流は数えない。

| 分類 | 条件 |
|---|---|
| 共有ノード | 交点のノードを共有し、入る線2・出る線2(水路は流下方向に描く決まりを使う) |
| 立体(記入あり) | ノードを共有せず、`tunnel` / `bridge` があるか `layer` が違う |
| 立体(記入なし) | ノードを共有せず、上下の記入もない(書き忘れか誤り) |

「直進」列は共有ノードのときだけ付く。入ってきた2本がそれぞれ進行方向±35°で別の出る線へ抜けていれば ○。
× は「合流してすぐ分流」の形の可能性がある。

設計は `docs/superpowers/specs/2026-10-31-water-crossing-design.md`。

## 結果(全国 8地方)

全 **9,351** 件。一覧は [CROSSINGS.md](CROSSINGS.md)、元データは `data/crossings.json`。

| 分類 | 件数 |
|---|---|
| 共有ノード | 5,244(うち直進 ○ 4,858) |
| 立体(記入あり) | 3,277 |
| 立体(記入なし) | 830 |

- 関門だった **玉川上水(way 60964194, `tunnel=yes`, `layer=-1`)× 残堀川(way 1117757672)** は「立体(記入あり)」で出る
- 多いのは用水路・小川どうし: ditch × ditch 2,385、stream × stream 1,945
- 交差に数えなかったもの: 線どうしの重なり 134 組、ノード未接続の端点 213

### 「自然の川どうしは交差しない」仮説

river × river は **490 件**(共有ノード 273、立体記入あり 163、記入なし 54)出た。ただし中身はまだ確かめていない。

- 490件のうち **125件は同じ名前の川どうし**(106件が共有ノード)。網状に分かれてまた合わさる流路や、
  同じ川が複数の way に分かれて描かれたものが「入2出2」に当たっているとみられる。交差ではない可能性が高い
- 関東の例では、`坂川放水路`・`中川上流放水路`・`北千葉導水路` のような人工の流路に `river` が付いたものが混ざる
- 仮説を確かめるには、同名の組を外したうえで、残りを地図で見る必要がある

## 再現

```bash
uv sync
for r in hokkaido tohoku kanto chubu kansai chugoku shikoku kyushu; do
  osmium tags-filter ~/y-junctions-data/osm/$r-latest.osm.pbf w/waterway -o data/${r}_waterway.osm.pbf --overwrite
done
uv run scripts/watercross.py report data/{hokkaido,tohoku,kanto,chubu,kansai,chugoku,shikoku,kyushu}_waterway.osm.pbf \
  --json data/crossings.json --md CROSSINGS.md   # 約2分
uv run pytest
```

`data/*.pbf` はリポジトリに入れていない(上のコマンドで再生成できる)。

## データ

Geofabrik の抽出(`osmosis_replication_timestamp`): 四国 2025-11-28、関東 2025-12-05、
九州 2025-12-27、東北・関西 2025-12-28、中部 2025-12-29、中国 2025-12-30、北海道 2026-01-02。
© OpenStreetMap contributors (ODbL)。

## 限界

- すべて機械判定で、地図・現地での確認はしていない
- 向きを逆に描いた水路があると、共有ノードの入る/出るを取り違える
- 地方の切り出しが重なる境界で、重なり・未接続端点の件数は二重に数えている場合がある(交差は重複除去済み)
