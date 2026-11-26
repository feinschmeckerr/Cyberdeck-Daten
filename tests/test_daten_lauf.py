"""Durchlauf von werkzeuge/daten-lauf.sh und release.sh --trocken ohne Netz: ein Mini-App-Repo mit Platzhalter-Erzeugern
(schreiben kleine Dateien im Format der echten), erfundene OSM-Daten (keine echten Orte) und Quellen über file://.
Braucht bash, git und pyosmium (sonst übersprungen) – auf dem Mac wie unter Linux.

    python3 -m unittest discover -s tests
"""

import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

DATEN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATEN / "tests"))
from test_gebaeudeteile import kachel, vi  # noqa: E402

try:
    import osmium
except ImportError:  # pragma: no cover
    osmium = None

ERZEUGER_KOPF = textwrap.dedent('''\
    import json, sqlite3, sys
    from pathlib import Path
    K = Path(__file__).resolve().parents[2] / "kartendaten"
    ''')

ERZEUGER = {
    "suchindex": 'db = sqlite3.connect(K / "suchindex.sqlite"); db.execute("CREATE TABLE orte (name)"); '
                 'db.execute("INSERT INTO orte VALUES (\'Musterhalt\')"); db.commit()',
    "suchwoerter": 'db = sqlite3.connect(K / "suchwoerter.sqlite"); db.execute("CREATE TABLE w (w)"); db.commit()',
    "strassennetz": '(K / "strassennetz").mkdir(); (K / "strassennetz/info.json").write_text("{}"); '
                    '(K / "strassennetz/kanten_a.u1").write_bytes(bytes(3)); '
                    '(K / "strassennetz/kanten_b.i4").write_bytes(bytes(12))',
    "merkmale": textwrap.dedent('''\
        db = sqlite3.connect(K / "merkmale.sqlite")
        db.execute("CREATE TABLE m (id INTEGER PRIMARY KEY, typ TEXT, name TEXT, breite REAL, laenge REAL, osm_typ TEXT, "
                   "osm_id INTEGER, zelle_lat INTEGER, zelle_lon INTEGER, tags TEXT, form TEXT DEFAULT 'punkt')")
        db.execute("ALTER TABLE m RENAME TO merkmale")
        db.execute("CREATE INDEX merkmale_typ ON merkmale (typ, zelle_lat, zelle_lon)")
        db.executemany("INSERT INTO merkmale (typ, name, breite, laenge, osm_typ, osm_id, zelle_lat, zelle_lon, tags, form) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       [("highway=elevator", "", 50.0, 10.0, "n", 1, 5000, 1000, '{"highway":"elevator"}', "punkt"),
                        ("highway=steps", "", 50.0, 10.0, "w", 10, 5000, 1000, None, "linie")])
        db.execute("CREATE TABLE typen AS SELECT typ, COUNT(*) AS anzahl FROM merkmale GROUP BY typ")
        db.execute("CREATE TABLE formen AS SELECT typ, form, COUNT(*) AS anzahl FROM merkmale GROUP BY typ, form")
        db.execute("CREATE TABLE info (schluessel TEXT, wert TEXT)")
        db.execute("INSERT INTO info VALUES ('zelle_grad', '0.01')")
        db.commit()'''),
    "grenzen": 'ziel = sys.argv[sys.argv.index("--ziel") + 1]; assert "--land" in sys.argv; '
               'db = sqlite3.connect(ziel); db.execute("CREATE TABLE g (g)"); db.commit()',
    "gebaeude": textwrap.dedent('''\
        import gzip
        db = sqlite3.connect(K / "gebaeude.mbtiles")
        db.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
        db.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
        db.executemany("INSERT INTO metadata VALUES (?, ?)", [("fassung", "3"), ("json", json.dumps(
            {"vector_layers": [{"id": "gebaeude", "fields": {"h": "Number"}}]}))])
        db.execute("INSERT INTO tiles VALUES (15, 1, 2, ?)", (gzip.compress(bytes.fromhex(open(K / "kachel.hex").read())),))
        db.commit()'''),
    "geschosse": 'db = sqlite3.connect(K / "geschosse.sqlite"); db.execute("CREATE TABLE g (g)"); db.commit()',
    "eingaenge": 'db = sqlite3.connect(K / "eingaenge.sqlite"); db.execute("CREATE TABLE e (e)"); db.commit()',
    "objekt": 'db = sqlite3.connect(K / "objekt.sqlite"); db.execute("CREATE TABLE o (o)"); db.commit()',
}


def befehl(*argumente, **kw):
    return subprocess.run(argumente, check=True, capture_output=True, text=True, **kw)


@unittest.skipUnless(osmium and shutil.which("bash") and shutil.which("git"), "braucht pyosmium, bash und git")
class DatenLauf(unittest.TestCase):
    def setUp(self):
        self.ordner = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.ordner)
        # Mini-App-Repo mit Erzeugern auf dem Zweig ios
        app = self.ordner / "app"
        (app / "tools" / "erzeugen").mkdir(parents=True)
        (app / "piflux").mkdir()
        (app / "piflux" / "__init__.py").write_text("")
        for name, rumpf in ERZEUGER.items():
            (app / "tools" / "erzeugen" / f"{name}-erzeugen.py").write_text(ERZEUGER_KOPF + rumpf + "\n# --land\n")
        befehl("git", "init", "-q", "-b", "ios", str(app))
        befehl("git", "-C", str(app), "add", ".")
        befehl("git", "-C", str(app), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
               "commit", "-q", "-m", "Erzeuger")
        self.app = app
        # Quellen: erfundene OSM-Daten, Grundkarte (nur vorhanden), md5
        quelle = self.ordner / "quelle"
        quelle.mkdir()
        pbf = quelle / "berlin-latest.osm.pbf"
        with osmium.SimpleWriter(str(pbf)) as w:
            w.add_node(osmium.osm.mutable.Node(id=1, location=(10.0, 50.0), tags={"highway": "elevator", "level": "-1;0"}))
            w.add_node(osmium.osm.mutable.Node(id=2, location=(10.0, 50.001), tags={}))
            w.add_node(osmium.osm.mutable.Node(id=3, location=(10.001, 50.001), tags={
                "railway": "subway_entrance", "name": "Musterhalt", "level": "0"}))
            w.add_way(osmium.osm.mutable.Way(id=10, nodes=[1, 2], tags={"highway": "steps", "conveying": "forward",
                                                                       "level": "-1;0"}))
            w.add_way(osmium.osm.mutable.Way(id=3, nodes=[1, 2, 3, 1], tags={"building:part": "roof", "layer": "1"}))
        (quelle / "berlin-latest.osm.pbf.md5").write_text(hashlib.md5(pbf.read_bytes()).hexdigest() + "  x\n")
        (quelle / "brandenburg-shortbread-1.0.mbtiles").write_bytes(b"Grundkarte")
        self.quelle = quelle
        # die Kachel für den Platzhalter-Erzeuger der Gebäude: Teil 14 (Weg 3, Bit 1)
        self.kachel = kachel([(14, [0, 0])], ["h"], [vi(5 << 3) + vi(4)]).hex()

    def umgebung(self):
        return {**os.environ, "PYTHON": sys.executable, "CYBERDECK_GEOFABRIK": self.quelle.as_uri(),
                "CYBERDECK_OSMFR": (self.quelle / "fehlt.pbf").as_uri(),
                "CYBERDECK_VG250": (self.quelle / "fehlt.zip").as_uri(), "CYBERDECK_APP": "", "CYBERDECK_AUSGABE": "",
                "CYBERDECK_OHNE_TESTS": "1"}  # die Tests laufen schon – nicht im Lauf noch einmal

    def test_lauf_und_release_trocken(self):
        ausgabe = self.ordner / "aus"
        # die Kachel legt der Platzhalter aus kartendaten/kachel.hex – über einen Erzeuger-Vorlauf
        erz = self.app / "tools" / "erzeugen" / "suchindex-erzeugen.py"
        erz.write_text(erz.read_text() + f"\n(K / 'kachel.hex').write_text('{self.kachel}')\n")
        befehl("git", "-C", str(self.app), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
               "commit", "-qam", "Kachel")
        ergebnis = subprocess.run(["bash", str(DATEN / "werkzeuge" / "daten-lauf.sh"), "--land", "berlin", "--app",
                                   str(self.app), "--ausgabe", str(ausgabe)], capture_output=True, text=True,
                                  env=self.umgebung())
        self.assertEqual(ergebnis.returncode, 0, ergebnis.stdout[-3000:] + ergebnis.stderr[-3000:])
        manifest = json.loads((ausgabe / "pakete" / "berlin.json").read_text())
        jePfad = {d["pfad"]: d for d in manifest["dateien"]}
        self.assertEqual(jePfad["merkmale.sqlite"]["fassung"], 2)
        self.assertEqual(jePfad["gebaeude.mbtiles"]["fassung"], 4)
        self.assertIn("grenzen.sqlite", jePfad)
        self.assertIn("strassennetz/info.json", jePfad)
        # die gepackte Merkmal-Datei trägt die Ebenen und die Rolltreppe
        roh = self.ordner / "m.sqlite"
        roh.write_bytes(gzip.decompress((ausgabe / "pakete" / jePfad["merkmale.sqlite"]["name"]).read_bytes()))
        db = sqlite3.connect(roh)
        self.assertEqual(db.execute("SELECT json_extract(tags, '$.level') FROM merkmale WHERE typ = 'highway=elevator'")
                         .fetchone()[0], "-1;0")
        self.assertEqual(db.execute("SELECT json_extract(tags, '$.conveying') FROM merkmale WHERE typ = 'highway=steps'")
                         .fetchone()[0], "forward")
        self.assertEqual(db.execute("SELECT name FROM merkmale WHERE typ = 'railway=subway_entrance'").fetchone()[0],
                         "Musterhalt")
        db.close()
        bericht = (ausgabe / "berichte" / "berlin.md").read_text()
        self.assertIn("Abweichungen bei alten Objekten/Feldern: 0", bericht)
        self.assertIn("mit bp 1", bericht)
        self.assertTrue((ausgabe / "lauf.json").is_file())
        self.assertFalse((ausgabe / "arbeit").exists())          # aufgeräumt
        self.assertEqual(befehl("git", "-C", str(self.app), "status", "--porcelain").stdout, "")  # App-Repo unberührt

        if not shutil.which("gh"):
            return
        trocken = subprocess.run(["bash", str(DATEN / "werkzeuge" / "release.sh"), "--ausgabe", str(ausgabe), "--trocken"],
                                 capture_output=True, text=True, env=self.umgebung())
        self.assertEqual(trocken.returncode, 0, trocken.stdout + trocken.stderr)
        self.assertIn("gh release create daten-", trocken.stdout)
        self.assertIn("mitnehmen.py", trocken.stdout)
        self.assertIn("bayern", trocken.stdout)                   # die anderen Länder kommen aus dem bisherigen Release
        # beschädigte Datei: release.sh verweigert
        datei = ausgabe / "pakete" / jePfad["suchindex.sqlite"]["name"]
        datei.write_bytes(datei.read_bytes() + b"x")
        kaputt = subprocess.run(["bash", str(DATEN / "werkzeuge" / "release.sh"), "--ausgabe", str(ausgabe), "--trocken"],
                                capture_output=True, text=True, env=self.umgebung())
        self.assertNotEqual(kaputt.returncode, 0)

    def test_trocken_und_falsches_land(self):
        trocken = subprocess.run(["bash", str(DATEN / "werkzeuge" / "daten-lauf.sh"), "--land", "berlin", "--app",
                                  str(self.app), "--ausgabe", str(self.ordner / "aus"), "--trocken", "--welt", "--fahrplan",
                                  "--lod2"], capture_output=True, text=True,
                                 env={**self.umgebung(), "PATH": os.environ["PATH"]})
        # --welt braucht Node ≥ 22; ohne Node scheitert es mit klarer Meldung
        if shutil.which("node"):
            self.assertEqual(trocken.returncode, 0, trocken.stdout[-2000:] + trocken.stderr[-2000:])
            for wort in ("bahnhof.py", "gebaeudeteile.py", "welt-osm.mjs", "oepnv-erzeugen.py", "lod2-dach-erzeugen.py"):
                self.assertIn(wort, trocken.stdout)
            self.assertFalse((self.ordner / "aus").exists())     # trocken: nichts angelegt
        else:
            self.assertIn("Node", trocken.stderr)
        falsch = subprocess.run(["bash", str(DATEN / "werkzeuge" / "daten-lauf.sh"), "--land", "atlantis", "--app",
                                 str(self.app), "--trocken"], capture_output=True, text=True, env=self.umgebung())
        self.assertNotEqual(falsch.returncode, 0)
        self.assertIn("Unbekanntes Land", falsch.stderr)


if __name__ == "__main__":
    unittest.main()
