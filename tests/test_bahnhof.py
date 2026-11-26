"""Prüfung von werkzeuge/bahnhof.py (Merkmal-Index für Bahnhöfe) ohne Rohdaten und ohne pyosmium – nur erfundene
Beispiele, keine echten Orte.

    python3 -m unittest discover -s tests
"""

import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "werkzeuge"))
import bahnhof  # noqa: E402


SCHEMA = """CREATE TABLE merkmale (id INTEGER PRIMARY KEY, typ TEXT, name TEXT, breite REAL, laenge REAL,
    osm_typ TEXT, osm_id INTEGER, zelle_lat INTEGER, zelle_lon INTEGER, tags TEXT, form TEXT DEFAULT 'punkt')"""


class Bahnhof(unittest.TestCase):
    def index(self):
        db = sqlite3.connect(":memory:")
        db.execute(SCHEMA)
        db.execute("CREATE INDEX merkmale_typ ON merkmale (typ, zelle_lat, zelle_lon)")
        db.execute("CREATE TABLE typen AS SELECT typ, 0 AS anzahl FROM merkmale")
        db.execute("CREATE TABLE formen AS SELECT typ, form, 0 AS anzahl FROM merkmale")
        db.execute("CREATE TABLE info (schluessel TEXT, wert TEXT)")
        db.execute("INSERT INTO info VALUES ('zelle_grad', '0.01')")
        db.executemany("INSERT INTO merkmale (typ, name, breite, laenge, osm_typ, osm_id, zelle_lat, zelle_lon, tags, form) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                           ("highway=elevator", "", 50.0, 10.0, "n", 1, 5000, 1000, '{"highway":"elevator"}', "punkt"),
                           ("railway=platform", "Musterhalt", 50.0, 10.0, "w", 2, 5000, 1000, '{"railway":"platform"}', "punkt"),
                           ("highway=bus_stop", "Musterweg", 50.0, 10.0, "n", 3, 5000, 1000, '{"highway":"bus_stop"}', "punkt"),
                           ("highway=steps", "", 50.0, 10.0, "w", 4, 5000, 1000, None, "linie"),
                           ("highway=steps", "", 50.001, 10.0, "w", 4, 5000, 1000, None, "linie"),
                           ("railway=station", "Musterhalt", 50.0, 10.0, "n", 5, 5000, 1000, '{"railway":"station"}', "punkt"),
                           ("highway=elevator", "", 50.0, 10.0, "n", 9, 5000, 1000, '{"highway":"elevator"}', "punkt"),
                       ])
        return db

    def test_ergaenzen(self):
        db = self.index()
        e = bahnhof.Ergaenzung(db)
        e.objekt("n", 1, {"highway": "elevator", "level": "-1;0", "door": "slide", "note": "x"}, (50.0, 10.0))
        e.objekt("w", 2, {"railway": "platform", "public_transport": "platform", "level": "-2", "railway:track_ref": "1"},
                 (50.0, 10.0))
        e.objekt("n", 3, {"highway": "bus_stop", "public_transport": "platform", "level": "0"}, (50.0, 10.0))
        e.objekt("w", 4, {"highway": "steps", "conveying": "forward", "incline": "up", "level": "-1;0"}, (50.0, 10.0),
                 [(50.0, 10.0), (50.001, 10.0)])
        e.objekt("w", 6, {"highway": "steps", "conveying": "yes"}, (50.0, 10.0), [(50.0, 10.0), (50.002, 10.0)])
        e.objekt("w", 7, {"highway": "steps"}, (50.0, 10.0), [(50.0, 10.0), (50.002, 10.0)])
        e.objekt("n", 8, {"railway": "subway_entrance", "name": "Musterhalt", "wheelchair": "no", "level": "0"}, (50.0, 10.0))
        e.objekt("n", 9, {"highway": "elevator", "railway": "subway_entrance", "level": "0"}, (50.0, 10.0))
        e.objekt("n", 5, {"railway": "station", "public_transport": "station"}, (50.0, 10.0))
        e.objekt("w", 10, {"public_transport": "station", "building": "train_station", "name": "Musterhalt"}, (50.0, 10.0))
        e.objekt("w", 11, {"highway": "platform", "public_transport": "platform", "ref": "A", "bus": "yes"}, (50.0, 10.0))
        e.schreiben()
        tags = {(t, i, b): json.loads(j) if j else None
                for t, i, b, j in db.execute("SELECT typ, osm_id, breite, tags FROM merkmale")}

        def eins(typ, osm_id):
            treffer = [v for (t, i, _b), v in tags.items() if t == typ and i == osm_id]
            self.assertEqual(len(treffer), 1, (typ, osm_id))
            return treffer[0]

        self.assertEqual(eins("highway=elevator", 1), {"highway": "elevator", "level": "-1;0", "door": "slide"})
        self.assertEqual(eins("railway=platform", 2)["railway:track_ref"], "1")
        self.assertEqual(eins("highway=bus_stop", 3), {"highway": "bus_stop"})  # Bushalt bleibt, wie er war
        self.assertNotIn(("public_transport=platform", 3), {(t, i) for t, i, _b in tags})
        self.assertNotIn(("public_transport=platform", 2), {(t, i) for t, i, _b in tags})
        treppe = [v for (t, i, _b), v in tags.items() if t == "highway=steps" and i == 4]
        self.assertEqual(treppe, [{"conveying": "forward", "level": "-1;0", "incline": "up"}] * 2)
        self.assertEqual(eins("highway=steps", 6), {"conveying": "yes"})    # neu, in der Mitte
        self.assertEqual([b for (t, i, b) in tags if i == 6], [50.001])
        self.assertNotIn(7, {i for _t, i, _b in tags})                     # gewöhnliche Treppe: nichts
        self.assertEqual(eins("railway=subway_entrance", 8)["level"], "0")
        # Aufzug, der zugleich Zugang ist: eine Zeile (der Aufzug) mit den Angaben
        self.assertNotIn(("railway=subway_entrance", 9), {(t, i) for t, i, _b in tags})
        self.assertEqual(eins("highway=elevator", 9), {"highway": "elevator", "level": "0"})
        e2 = bahnhof.Ergaenzung(db)  # Aufzug ohne Zeile im Index (stand unter anderer Art): keine neue Zeile
        e2.objekt("n", 12, {"highway": "elevator", "shop": "kiosk", "level": "1"}, (50.0, 10.0))
        self.assertEqual(e2.neu, {})
        self.assertNotIn(("public_transport=station", 5), {(t, i) for t, i, _b in tags})
        self.assertEqual(eins("public_transport=station", 10)["name"], "Musterhalt")
        self.assertEqual(eins("public_transport=platform", 11), {"ref": "A", "bus": "yes", "highway": "platform",
                                                                 "public_transport": "platform"})
        info = dict(db.execute("SELECT schluessel, wert FROM info"))
        self.assertEqual(info["fassung"], "2")
        zahlen = json.loads(info["bahnhof"])
        self.assertEqual(zahlen["highway=elevator"], {"anzahl": 2, "mit_level": 2})
        self.assertEqual(zahlen["rolltreppe"], {"anzahl": 2, "mit_level": 1})
        self.assertEqual(dict(db.execute("SELECT typ, anzahl FROM typen"))["highway=steps"], 3)
        # nach Art geordnet (wie im Erzeuger) und Index wieder da
        typen = [t for (t,) in db.execute("SELECT typ FROM merkmale ORDER BY id")]
        self.assertEqual(typen, sorted(typen))
        self.assertTrue(db.execute("SELECT 1 FROM sqlite_schema WHERE name = 'merkmale_typ'").fetchone())


if __name__ == "__main__":
    unittest.main()
