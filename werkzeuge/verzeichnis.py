"""Fasst die Manifeste der Länder (<land>.json) zu pakete.json zusammen – das Verzeichnis, das die App lädt.

Fassung des Verzeichnisses bleibt 1 (ältere Apps lehnen alles andere ab); Neues kommt nur als zusätzliche Felder, die
ältere Apps übergehen: „arten“ (was die Dateien bzw. Pakete enthalten, mit Fassung) und Zusatzpakete wie „lod2-berlin“
in „laender“ (Manifest mit art, fuer, optional, lizenz – ältere Apps fragen nur nach Ländern, die sie kennen).
Beschreibung des Formats: docs/pakete-format.md.

    python3 werkzeuge/verzeichnis.py <ordner mit den Manifesten> <release-tag> > pakete.json
"""

import json
import sys
import time
from pathlib import Path

QUELLEN = ("© OpenStreetMap-Mitwirkende, ODbL 1.0 (https://www.openstreetmap.org/copyright), "
           "über Geofabrik (https://download.geofabrik.de) und VersaTiles (https://versatiles.org); "
           "Verwaltungsgrenzen (Kreise, Gemeinden, grenzen.sqlite): © GeoBasis-DE / BKG (VG250), dl-de/by-2-0 "
           "(https://www.govdata.de/dl-de/by-2-0), vereinfacht; "
           "Welt-Übersicht: Natural Earth (gemeinfrei); "
           "Fahrplan: VBB Verkehrsverbund Berlin-Brandenburg GmbH, CC BY 4.0 (https://www.vbb.de/vbbgtfs); "
           "3D-Dächer Berlin (lod2-berlin): Senatsverwaltung für Stadtentwicklung, Bauen und Wohnen Berlin, LoD2, "
           "dl-de/zero-2.0 (https://www.govdata.de/dl-de/zero-2-0); "
           "3D-Dächer Brandenburg (lod2-brandenburg): © GeoBasis-DE/LGB, dl-de/by-2.0 (https://www.govdata.de/dl-de/by-2-0), "
           "vereinfacht")

# Was in den Dateien eines Pakets steckt (Feld „art“ je Datei bzw. je Zusatzpaket) – für neuere Apps
ARTEN = {
    "suchindex": {"name": "Suche"}, "suchwoerter": {"name": "Tippfehler-Wörter"},
    "merkmale": {"name": "Merkmale", "fassung": 2,
                 "inhalt": "Bahnhöfe: level & Co. an Aufzügen und Bahnsteigen, Rolltreppen (highway=steps + conveying), "
                           "railway=subway_entrance/train_station_entrance, public_transport=platform/station"},
    "strassennetz": {"name": "Straßennetz"}, "grenzen": {"name": "Verwaltungsgrenzen"},
    "gebaeude": {"name": "3D-Gebäude", "fassung": 4,
                 "inhalt": "Feature-ID (OSM-Kennung*4+Art) und Felder h, m, s, l, u, r, b, rs; eltern, bp, ml, xl, ly bei "
                           "Gebäudeteilen"},
    "geschosse": {"name": "Geschosse (OSM)"},
    "eingaenge": {"name": "Eingänge", "fassung": 2, "inhalt": "zusätzlich ebene, strasse, hausnummer, plz, ort, einheit, breite_m, hoehe_m"},
    "objekt": {"name": "Objektakte", "fassung": 1,
               "inhalt": "Einspeisung, Feuermelder, Rettungspunkt, Sammelplatz, Zufahrt, Durchfahrt, Tiefgarage, Parkhaus, Einfahrt, PV"},
    "lod2": {"name": "3D-Dächer (LoD2)", "fassung": 2, "inhalt": "Höfe richtig zerlegt", "optional": True,
             "nur": ["berlin", "brandenburg"]},
    "oepnv": {"name": "Fahrplan"}, "welt": {"name": "Welt-Übersicht"}, "welt-osm": {"name": "Welt-Straßenkarte"},
}

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    ordner, tag = Path(sys.argv[1]), sys.argv[2]
    # pakete.json selbst nie mitlesen (release.sh leitet die Ausgabe früher in denselben Ordner – leere Datei)
    laender = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(ordner.glob("*.json")) if p.name != "pakete.json"]
    json.dump({"version": 1, "tag": tag, "erzeugt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "basis": f"https://github.com/feinschmeckerr/Cyberdeck-Daten/releases/download/{tag}/",
               "lizenz": QUELLEN, "arten": ARTEN, "laender": laender}, sys.stdout, ensure_ascii=False, indent=1)
