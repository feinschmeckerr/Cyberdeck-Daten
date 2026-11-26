"""Prüfung von werkzeuge/gebaeudeteile.py (gebaeude.mbtiles Fassung 4) ohne Rohdaten und ohne pyosmium – nur
erfundene Beispiele, keine echten Orte.

    python3 -m unittest discover -s tests
"""

import gzip
import json
import sqlite3
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "werkzeuge"))
import gebaeudeteile as teile  # noqa: E402


# ---------- kleine MVT-Hilfen für die Beispiele (unabhängig vom Werkzeug geschrieben) ----------

def vi(n):
    out = bytearray()
    while n > 0x7F:
        out.append(n & 0x7F | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def feld(nr, daten):
    return vi(nr << 3 | 2) + vi(len(daten)) + daten


def kachel(objekte, schluessel, werte):
    """objekte: [(id, [k, v, k, v …])]; werte: Bytes der Value-Nachrichten."""
    ebene = vi(15 << 3) + vi(2) + feld(1, b"gebaeude")
    geo = b"".join(vi(x) for x in (9, 0, 0, 18, 20, 0, 0, 20, 15))
    for fid, tags in objekte:
        ebene += feld(2, vi(1 << 3) + vi(fid) + feld(2, b"".join(vi(t) for t in tags)) + vi(3 << 3) + vi(3) + feld(4, geo))
    ebene += b"".join(feld(3, k.encode()) for k in schluessel) + b"".join(feld(4, w) for w in werte)
    ebene += vi(5 << 3) + vi(4096)
    return feld(3, ebene)


def lesen(daten):
    """Kachel → {id: {schlüssel: wert}} über die Lesefunktionen des Werkzeugs (Werte über wert_lesen)."""
    ergebnis = {}
    for nr, _t, ebene, _r in teile.felder_lesen(daten):
        if nr != 3:
            continue
        teile_e = teile.felder_lesen(bytes(ebene))
        ks = [bytes(w).decode() for n, _t, w, _r in teile_e if n == 3]
        ws = [teile.wert_lesen(bytes(w))[1] for n, _t, w, _r in teile_e if n == 4]
        for n, _t, w, _r in teile_e:
            if n != 2:
                continue
            o = teile.felder_lesen(bytes(w))
            fid = next(x for m, _t, x, _r in o if m == 1)
            roh = next(bytes(x) for m, _t, x, _r in o if m == 2)
            tags, i = [], 0
            while i < len(roh):
                v, i = teile._lies_varint(roh, i)
                tags.append(v)
            ergebnis[fid] = {ks[a]: ws[b] for a, b in zip(tags[0::2], tags[1::2])}
    return ergebnis


class Gebaeudeteile(unittest.TestCase):
    def test_felder(self):
        self.assertEqual(teile.felder({"building:part": "roof", "min_level": "-2", "max_level": "0", "layer": "-1"}),
                         {"bp": "roof", "ml": -2, "xl": 0, "ly": -1})
        self.assertEqual(teile.felder({"building:part": "yes", "level": "-2;-1"}), {"ml": -2, "xl": -1})
        self.assertEqual(teile.felder({"building:part": "yes", "level": "0-2", "max_level": "3"}), {"xl": 3})
        self.assertEqual(teile.felder({"building:part": "Platform", "layer": "1.5"}), {"bp": "platform"})
        self.assertEqual(teile.felder({"building:part": "yes", "layer": "99"}), {})

    def test_ebenen(self):
        self.assertEqual(teile.ebenen("-1;0"), [-1, 0])
        self.assertEqual(teile.ebenen("-2--1"), [-2, -1])
        self.assertEqual(teile.ebenen("0-2"), [0, 1, 2])
        self.assertEqual(teile.ebenen("U1"), [])

    def test_ist_teil_wie_erzeuger(self):
        self.assertTrue(teile.ist_teil({"building:part": "yes"}))
        self.assertFalse(teile.ist_teil({"building:part": "yes", "building": "yes"}))
        self.assertFalse(teile.ist_teil({"building:part": "no"}))
        self.assertEqual(teile.kennung(10, False), 42)
        self.assertEqual(teile.kennung(10, True), 43)

    def test_kachel(self):
        # Gebäude 40 (Teil-Bit 0), Teile 42 und 43; Werte: h 12 (uint), b "roof" (Text)
        werte = [vi(5 << 3) + vi(12), feld(1, b"roof")]
        daten = kachel([(40, [0, 0]), (42, [0, 0]), (43, [0, 0, 1, 1])], ["h", "b"], werte)
        self.assertEqual(teile.kachel_ergaenzen(daten, {}), (daten, set()))
        neu, ids = teile.kachel_ergaenzen(daten, {40: {"bp": "x"}, 42: {"bp": "roof", "ml": -1, "xl": 12, "ly": 2},
                                                  43: {"ml": 0.5}})
        self.assertEqual(ids, {42, 43})
        gelesen = lesen(neu)
        self.assertEqual(gelesen[40], {"h": 12})                     # kein Teil: unverändert
        self.assertEqual(gelesen[42], {"h": 12, "bp": "roof", "ml": -1, "xl": 12, "ly": 2})
        self.assertEqual(gelesen[43], {"h": 12, "b": "roof", "ml": 0.5})

    def test_vorhandenes_feld_bleibt(self):
        daten = kachel([(42, [0, 0])], ["bp"], [feld(1, b"tower")])
        neu, ids = teile.kachel_ergaenzen(daten, {42: {"bp": "roof"}})
        self.assertEqual((neu, ids), (daten, set()))

    def test_datei(self):
        with tempfile.TemporaryDirectory() as ordner:
            pfad = Path(ordner) / "gebaeude.mbtiles"
            db = sqlite3.connect(pfad)
            db.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
            db.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
            db.executemany("INSERT INTO metadata VALUES (?, ?)", [
                ("fassung", "3"), ("json", json.dumps({"vector_layers": [{"id": "gebaeude", "fields": {"h": "Number"}}]}))])
            daten = kachel([(42, [0, 0])], ["h"], [vi(5 << 3) + vi(9)])
            db.execute("INSERT INTO tiles VALUES (15, 1, 2, ?)", (gzip.compress(daten),))
            db.execute("INSERT INTO tiles VALUES (14, 0, 1, ?)", (gzip.compress(daten),))
            db.commit()
            db.close()
            zahlen = teile.ergaenzen(pfad, {42: {"bp": "platform", "ly": -1}})
            self.assertEqual((zahlen["objekte"], zahlen["teile_mit_bp"], zahlen["teile_mit_layer"]), (2, 1, 1))
            db = sqlite3.connect(pfad)
            meta = dict(db.execute("SELECT name, value FROM metadata"))
            self.assertEqual(meta["fassung"], "4")
            self.assertEqual(json.loads(meta["json"])["vector_layers"][0]["fields"]["bp"], "String")
            for (blob,) in db.execute("SELECT tile_data FROM tiles"):
                self.assertEqual(lesen(gzip.decompress(blob))[42], {"h": 9, "bp": "platform", "ly": -1})
            db.close()
            with self.assertRaises(SystemExit):  # zweimal ergänzen geht nicht
                teile.ergaenzen(pfad, {})

    def test_werte(self):
        self.assertEqual(teile.wert_lesen(teile.wert_schreiben(-3)), ("i", -3))
        self.assertEqual(teile.wert_lesen(teile.wert_schreiben(7)), ("i", 7))
        self.assertEqual(teile.wert_lesen(teile.wert_schreiben(1.5)), ("f", 1.5))
        self.assertEqual(teile.wert_lesen(vi(2 << 3 | 5) + struct.pack("<f", 2.5)), ("f", 2.5))

if __name__ == "__main__":
    unittest.main()
