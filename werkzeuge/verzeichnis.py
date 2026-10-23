"""Fasst die Manifeste der Länder (<land>.json) zu pakete.json zusammen – das Verzeichnis, das die App lädt.

    python3 werkzeuge/verzeichnis.py <ordner mit den Manifesten> <release-tag> > pakete.json
"""

import json
import sys
import time
from pathlib import Path

QUELLEN = ("© OpenStreetMap-Mitwirkende, ODbL 1.0 (https://www.openstreetmap.org/copyright), "
           "über Geofabrik (https://download.geofabrik.de) und VersaTiles (https://versatiles.org); "
           "Welt-Übersicht: Natural Earth (gemeinfrei); "
           "Fahrplan: VBB Verkehrsverbund Berlin-Brandenburg GmbH, CC BY 4.0 (https://www.vbb.de/vbbgtfs)")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    ordner, tag = Path(sys.argv[1]), sys.argv[2]
    laender = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(ordner.glob("*.json"))]
    json.dump({"version": 1, "tag": tag, "erzeugt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "basis": f"https://github.com/feinschmeckerr/Cyberdeck-Daten/releases/download/{tag}/",
               "lizenz": QUELLEN, "laender": laender}, sys.stdout, ensure_ascii=False, indent=1)
