"""verzeichnis.py: liest nur Manifeste, nie die eigene (womöglich leere) pakete.json."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WERKZEUG = Path(__file__).resolve().parent.parent / "werkzeuge" / "verzeichnis.py"


class Verzeichnis(unittest.TestCase):
    def test_leere_pakete_json_im_ordner(self):
        ordner = Path(tempfile.mkdtemp())
        (ordner / "land.json").write_text(json.dumps({"id": "land", "dateien": []}), encoding="utf-8")
        (ordner / "pakete.json").write_text("", encoding="utf-8")  # so legte die Shell sie früher an
        ergebnis = subprocess.run([sys.executable, str(WERKZEUG), str(ordner), "daten-test"], capture_output=True,
                                  text=True, check=True)
        verzeichnis = json.loads(ergebnis.stdout)
        self.assertEqual([land["id"] for land in verzeichnis["laender"]], ["land"])
        self.assertEqual(verzeichnis["tag"], "daten-test")


if __name__ == "__main__":
    unittest.main()
