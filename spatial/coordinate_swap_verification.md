# Annex 4 coordinate-order verification (2026-11-06)

Source: `data/raw/青海省交通运输厅.pdf` (47 pp., sha256
`b1df71b90c5706c1adb26211590bd90aa58005a0213ecc53c2315bf3b38f7d9d`).
The Annex 4 table header is "单位纬度 | 单位经度" (latitude, longitude).

| seq | team | PDF page | values as printed | correct order |
|---|---|---|---|---|
| 5 | 海晏西海湿地水上运动有限公司水上应急救援队伍 | 42 | 100.826463, 37.00166 | lat 37.00166, lon 100.826463 |
| 24 | 共和公路段应急保障队 | 45 | 100.612014, 36.257456 | lat 36.257456, lon 100.612014 |

Both rows print longitude first and latitude second, i.e. the field order is
reversed relative to the header. The extraction-time flag
`latlon:swapped_in_source_recorded` is therefore CORRECT, and the
normalised (lat, lon) pairs stored in `team_location_audit.csv` are the
right ones (both fall inside Qinghai: lat 36-37 N, lon 100-101 E).

## Consequence for the primary pool

The two records remain EXCLUDED from the 39-crew OSM primary pool, but no
longer because they await verification. The remaining reasons are:

1. the coordinate datum is not declared in the source (`unknown`);
2. the values are organisation-location proxies, not verified vehicle depots.

The route matrix is unchanged at 39 x 28 = 1092 pairs (P0-1 fix), and the
NET-E1a/NET-E1b dispatch results are unaffected.
