"""Bericht der Bahnhof-Probe (.github/workflows/bahnhof-probe.yml) als Markdown: Abdeckung der neuen Angaben,
Größen vorher/nachher (roh und gzip) und Gegenprobe der Kacheln (Objekte, IDs, Geometrie und alte Felder unverändert).

    python3 werkzeuge/probe_bericht.py <ordner vorher> <ordner nachher>
"""

import collections
import gzip
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gebaeudeteile as teile  # noqa: E402


def groesse(pfad):
    roh = pfad.read_bytes()
    return len(roh), len(gzip.compress(roh, 6))


def mb(n):
    return f"{n / 1e6:.2f} MB"


def merkmale(vorher, nachher):
    a, b = sqlite3.connect(vorher), sqlite3.connect(nachher)
    print("## merkmale.sqlite\n")
    print("| Art | Zeilen vorher | nachher | mit level vorher | mit level nachher |\n|---|---|---|---|---|")
    for typ in ("highway=elevator", "railway=platform", "public_transport=platform", "railway=subway_entrance",
                "railway=train_station_entrance", "public_transport=station"):
        werte = []
        for db in (a, b):
            werte.append(db.execute("SELECT COUNT(*), COUNT(json_extract(tags, '$.level')) FROM merkmale WHERE typ = ? "
                                    "AND form = 'punkt'", (typ,)).fetchone())
        print(f"| `{typ}` | {werte[0][0]:,} | {werte[1][0]:,} | {werte[0][1]:,} | {werte[1][1]:,} |")
    for name, db in (("vorher", a), ("nachher", b)):
        n, l = db.execute("SELECT COUNT(*), COUNT(level) FROM (SELECT MAX(json_extract(tags, '$.level')) AS level "
                          "FROM merkmale WHERE typ = 'highway=steps' AND tags LIKE '%conveying%' GROUP BY osm_typ, osm_id)"
                          ).fetchone()
        print(f"\nRolltreppen ({name}, je OSM-Weg): {n:,}, davon mit level {l:,}")
    print("\nAngaben an Aufzügen und Bahnsteigen (nachher, Zeilen mit dem Tag):\n")
    for typ, schluessel in (("highway=elevator", ("level", "repeat_on", "level:ref", "wheelchair:description", "door",
                                                  "width", "capacity")),
                            ("railway=platform", ("level", "layer", "ref", "railway:track_ref", "local_ref", "height",
                                                  "tactile_paving", "covered"))):
        teile_text = []
        for k in schluessel:
            n = b.execute(f"SELECT COUNT(*) FROM merkmale WHERE typ = ? AND json_extract(tags, '$.\"{k}\"') IS NOT NULL",
                          (typ,)).fetchone()[0]
            teile_text.append(f"`{k}` {n:,}")
        print(f"- `{typ}`: " + ", ".join(teile_text))
    print(f"\ninfo bahnhof: `{dict(b.execute('SELECT schluessel, wert FROM info')).get('bahnhof')}`\n")
    a.close()
    b.close()


def kachel_objekte(daten):
    """{(ebene, id): (geometrie, {schlüssel: wert})} einer Kachel."""
    ergebnis = {}
    for nr, _t, ebene, _r in teile.felder_lesen(daten):
        if nr != 3:
            continue
        felder = teile.felder_lesen(bytes(ebene))
        name = next(bytes(w).decode() for n, _t, w, _r in felder if n == 1)
        ks = [bytes(w).decode() for n, _t, w, _r in felder if n == 3]
        ws = [teile.wert_lesen(bytes(w)) for n, _t, w, _r in felder if n == 4]
        for n, _t, w, _r in felder:
            if n != 2:
                continue
            o = teile.felder_lesen(bytes(w))
            fid = next((x for m, _t, x, _r in o if m == 1), None)
            geo = next((bytes(x) for m, _t, x, _r in o if m == 4), b"")
            roh = next((bytes(x) for m, _t, x, _r in o if m == 2), b"")
            tags, i = [], 0
            while i < len(roh):
                v, i = teile._lies_varint(roh, i)
                tags.append(v)
            ergebnis[(name, fid, len(ergebnis) if fid is None else 0)] = (geo, {ks[x]: ws[y] for x, y in zip(tags[0::2], tags[1::2])})
    return ergebnis


def gebaeude(vorher, nachher):
    a, b = sqlite3.connect(vorher), sqlite3.connect(nachher)
    meta_a, meta_b = dict(a.execute("SELECT name, value FROM metadata")), dict(b.execute("SELECT name, value FROM metadata"))
    print("## gebaeude.mbtiles\n")
    print(f"Fassung {meta_a.get('fassung')} → {meta_b.get('fassung')}; teile_mit_bp {meta_b.get('teile_mit_bp')}, "
          f"teile_mit_ebene {meta_b.get('teile_mit_ebene')}, teile_mit_layer {meta_b.get('teile_mit_layer')}\n")
    alt = {(z, x, y): d for z, x, y, d in a.execute("SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles")}
    fehler, geaendert, teil_ids, mit_rs, felder_z15 = 0, 0, set(), set(), collections.Counter()
    arten = collections.Counter()
    for z, x, y, d in b.execute("SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles"):
        if (z, x, y) not in alt:
            fehler += 1
            continue
        if d == alt[(z, x, y)]:
            vor = nach = None
        else:
            geaendert += 1
            vor, nach = kachel_objekte(gzip.decompress(alt[(z, x, y)])), kachel_objekte(gzip.decompress(d))
            if vor.keys() != nach.keys():
                fehler += 1
            for k, (geo, eig) in vor.items():
                geo2, eig2 = nach.get(k, (None, {}))
                if geo != geo2 or any(eig2.get(s) != w for s, w in eig.items()):
                    fehler += 1
        if z != 15:
            continue
        for (_e, fid, _n), (_g, eig) in (nach or kachel_objekte(gzip.decompress(d))).items():
            if fid is not None and fid >> 1 & 1:
                teil_ids.add(fid)
                if "rs" in eig:
                    mit_rs.add(fid)
                for s in ("bp", "ml", "xl", "ly"):
                    if s in eig:
                        felder_z15[s] += 1
                if "bp" in eig:
                    arten[eig["bp"][1]] += 1
    print(f"Gegenprobe: {len(alt):,} Kacheln, {geaendert:,} ergänzt, Abweichungen bei alten Objekten/Feldern: {fehler}\n")
    print(f"Gebäudeteile in Zoom 15: {len(teil_ids):,}; mit rs (roof:shape) {len(mit_rs):,}; "
          + ", ".join(f"mit {s} {felder_z15[s]:,}" for s in ("bp", "ml", "xl", "ly")) + "\n")
    print("Häufigste bp: " + ", ".join(f"`{k}` {n:,}" for k, n in arten.most_common(12)) + "\n")
    a.close()
    b.close()
    return fehler


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    vorher, nachher = Path(sys.argv[1]), Path(sys.argv[2])
    print("## Größen\n\n| Datei | vorher | nachher | gzip vorher | gzip nachher |\n|---|---|---|---|---|")
    for name in ("merkmale.sqlite", "gebaeude.mbtiles"):
        (ra, ga), (rb, gb) = groesse(vorher / name), groesse(nachher / name)
        print(f"| {name} | {mb(ra)} | {mb(rb)} | {mb(ga)} | {mb(gb)} |")
    print()
    merkmale(vorher / "merkmale.sqlite", nachher / "merkmale.sqlite")
    if gebaeude(vorher / "gebaeude.mbtiles", nachher / "gebaeude.mbtiles"):
        sys.exit("Gegenprobe der Kacheln: alte Objekte oder Felder verändert")


if __name__ == "__main__":
    main()
