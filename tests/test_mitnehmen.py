"""mitnehmen.py: Hochladen mit neuen Versuchen und Fortsetzen nach einem Abbruch (ohne Netz, gh ist ersetzt)."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "werkzeuge"))
import mitnehmen  # noqa: E402


class FalschesGh:
    """Spielt gh: hält zwei Releases als Wörterbücher, lässt die ersten `fehler` Uploads scheitern."""

    def __init__(self, alt, neu, fehler=0):
        self.alt, self.neu, self.fehler, self.hochgeladen = alt, neu, fehler, []

    def __call__(self, *argumente):
        befehl, tag = argumente[1], argumente[2]
        if befehl == "download":
            ordner, name = Path(argumente[argumente.index("-D") + 1]), argumente[argumente.index("--pattern") + 1]
            (ordner / name).write_bytes(self.alt[name])
            return ""
        if befehl == "upload":
            if self.fehler:
                self.fehler -= 1
                raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 502: Bad Gateway")
            pfad = Path(argumente[-1])
            self.neu[pfad.name] = pfad.read_bytes()
            self.hochgeladen.append(pfad.name)
            return ""
        raise AssertionError(argumente)


def manifest(dateien):
    return json.dumps({"dateien": [{"name": n, "gz_groesse": len(d), "gz_sha256": hashlib.sha256(d).hexdigest()}
                                   for n, d in dateien.items()]}).encode()


class Mitnehmen(unittest.TestCase):
    def setUp(self):
        self.dateien = {"land--a.gz": b"aaaa", "land--b.gz": b"bbbbbb"}
        self.alt = {**self.dateien, "land.json": manifest(self.dateien)}
        self.ordner = Path(tempfile.mkdtemp())
        self.alt_gh, self.alt_warten = mitnehmen.gh, mitnehmen.WARTEN_S
        mitnehmen.WARTEN_S = 0

    def tearDown(self):
        mitnehmen.gh, mitnehmen.WARTEN_S = self.alt_gh, self.alt_warten

    def test_wiederholt_gescheiterten_upload(self):
        mitnehmen.gh = FalschesGh(self.alt, {}, fehler=2)
        anzahl = mitnehmen.mitnehmen("land", "alt", "neu", "repo", self.ordner, set(self.alt))
        self.assertEqual(anzahl, 2)
        self.assertEqual(mitnehmen.gh.neu, self.alt)
        self.assertEqual(mitnehmen.gh.hochgeladen[-1], "land.json")  # Manifest zuletzt

    def test_gibt_nach_allen_versuchen_auf(self):
        mitnehmen.gh = FalschesGh(self.alt, {}, fehler=mitnehmen.HOCHLADEN_VERSUCHE)
        with self.assertRaises(subprocess.CalledProcessError):
            mitnehmen.mitnehmen("land", "alt", "neu", "repo", self.ordner, set(self.alt))
        self.assertNotIn("land.json", mitnehmen.gh.neu)  # unvollständiges Paket ohne Manifest

    def test_ueberspringt_was_schon_da_ist(self):
        neu = {"land--a.gz": b"aaaa"}
        mitnehmen.gh = FalschesGh(self.alt, neu)
        mitnehmen.mitnehmen("land", "alt", "neu", "repo", self.ordner, set(self.alt), {"land--a.gz": 4})
        self.assertEqual(mitnehmen.gh.hochgeladen, ["land--b.gz", "land.json"])

    def test_falsche_groesse_wird_neu_geladen(self):
        mitnehmen.gh = FalschesGh(self.alt, {"land--a.gz": b"aa"})
        mitnehmen.mitnehmen("land", "alt", "neu", "repo", self.ordner, set(self.alt), {"land--a.gz": 2})
        self.assertEqual(mitnehmen.gh.hochgeladen, ["land--a.gz", "land--b.gz", "land.json"])


if __name__ == "__main__":
    unittest.main()
