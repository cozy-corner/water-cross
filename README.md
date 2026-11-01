# 水路の交差点

玉川上水と残堀川のような「水路どうしの交差」を、OpenStreetMap から日本全国で探した記録。
趣味。

## 判定

線の水路 `waterway=river|stream|canal|drain|tidal_channel` の、別々の2本が交わる点を拾い、
次の2つを検出点として出す。合流・分流は出さない。言葉の意味は [docs/glossary.md](docs/glossary.md)。

`ditch`(道路脇の側溝や田の縁の溝)は対象外。道路と水路が交わる場所が、道路沿いの ditch の線を介して
検出点として出てしまうため(例: 35.41620, 139.31710)。

| 分類 | 条件 |
|---|---|
| 共有ノード | 交点のノードを共有し、入る線2・出る線2(水路は流下方向に描く決まりを使う)。ただし2本が同じ隣のノードへの区間を共有するもの(線を重ねて描いたもの)は除く(例: 35.72214, 139.33330) |
| 立体(記入あり) | ノードを共有せず、`tunnel` / `bridge` があるか `layer` が違う |

ノードを共有せず、上下を示すタグもない交点は出さない。データの上では交差として描かれておらず、
JOSM のバリデータ(Crossing waterways)が描き方の誤りとして警告する形のため。
「本当は交差で、タグを書き忘れただけ」の可能性は考えない(それを入れるとどの交点も外せなくなる)。

設計は `docs/superpowers/specs/2026-10-31-water-crossing-design.md`。

## 結果(全国 8地方)

全 **4,639** 件。一覧は [CROSSINGS.md](CROSSINGS.md)、元データは `data/crossings.json`。
地図で見るには `uv run scripts/make_map.py data/crossings.json map.html` で `map.html` を作り、ブラウザで開く(分類ごとに色分け、表示の切り替えあり。背景は地理院タイルの淡色地図、点からストリートビューへのリンクあり)。

| 分類 | 件数 |
|---|---|
| 共有ノード | 2,014 |
| 立体(記入あり) | 2,625 |

- 関門だった **玉川上水(way 60964194, `tunnel=yes`, `layer=-1`)× 残堀川(way 1117757672)** は「立体(記入あり)」で出る
- 多いのは小川どうし: stream × stream 1,391、次いで river × stream 920
- 検出点にしなかったもの: 線どうしの重なり 114 組、ノード未接続の端点 177、上下を示すタグのない交点 711

### 「自然の川どうしは交差しない」仮説

river × river は **317 件**(共有ノード 154、立体記入あり 163)出た。ただし中身はまだ確かめていない。

- 317件のうち **44件は同じ名前の川どうし**(35件が共有ノード)。網状に分かれてまた合わさる流路が
  「入2出2」に当たっているとみられ、交差ではない可能性が高い
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
- 立体(記入あり)は、線が交わっていることとタグしか見ていない。交点があっても交差とは限らない
- 向きを逆に描いた水路があると、共有ノードの入る/出るを取り違える。4本の合流が交差に見えることがある
- 共有ノードの入2出2には「合流してすぐ分流」する形も入っている。交差と区別していない
- 地方の切り出しが重なる境界で、重なり・未接続端点・タグのない交点の件数は二重に数えている場合がある(検出点は重複除去済み)
