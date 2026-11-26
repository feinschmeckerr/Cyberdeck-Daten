"""Prüft die fertigen Dateien eines Landes vor dem Packen (daten-lauf.sh): jede SQLite/MBTiles-Datei lesbar und heil
(PRAGMA quick_check), nicht leer, die Fassungen wie erwartet (merkmale 2 mit Bahnhof-Angaben, gebaeude 4 mit
Gebäudeteilen), das Straßennetz vollständig (info.json und gleich lange Kantenspalten).

    python3 werkzeuge/pruefen.py <ordner mit den Ergebnissen eines Landes>

Ausgang 1 bei einem Fehler; Abweichungen ohne Folgen für die App (z. B. ältere Fassung) nur als Hinweis.
"""

import json
import sqlite3
import sys
from pathlib import Path

PFLICHT = ("suchindex.sqlite", "suchwoerter.sqlite", "merkmale.sqlite", "gebaeude.mbtiles", "strassennetz")
FASSUNG = {"merkmale.sqlite": 2, "gebaeude.mbtiles": 4}


def fassung(db):
    for abfrage in ("SELECT wert FROM info WHERE schluessel = 'fassung'", "SELECT value FROM metadata WHERE name = 'fassung'"):
        try:
            zeile = db.execute(abfrage).fetchone()
        except sqlite3.Error:
            continue
        if zeile and str(zeile[0]).isdigit():
            return int(zeile[0])
    return None


def datenbank(pfad, fehler, hinweise):
    try:
        db = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
        ergebnis = db.execute("PRAGMA quick_check").fetchone()[0]
        if ergebnis != "ok":
            fehler.append(f"{pfad.name}: quick_check {ergebnis}")
        tabellen = [t for (t,) in db.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")]
        if not tabellen:
            fehler.append(f"{pfad.name}: keine Tabellen")
        soll = FASSUNG.get(pfad.name)
        if soll is not None and fassung(db) != soll:
            hinweise.append(f"{pfad.name}: Fassung {fassung(db)} statt {soll}")
        if pfad.name == "gebaeude.mbtiles" and not db.execute("SELECT 1 FROM tiles LIMIT 1").fetchone():
            fehler.append("gebaeude.mbtiles: keine Kacheln")
        if pfad.name == "merkmale.sqlite" and not db.execute("SELECT 1 FROM merkmale LIMIT 1").fetchone():
            fehler.append("merkmale.sqlite: keine Merkmale")
        db.close()
    except sqlite3.Error as e:
        fehler.append(f"{pfad.name}: {e}")


def strassennetz(ordner, fehler):
    info = ordner / "info.json"
    try:
        json.loads(info.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        fehler.append(f"strassennetz/info.json: {e}")
    # Kantenspalten (kanten_*.<typ><bytes>) müssen gleich viele Einträge haben
    laengen = {}
    for datei in ordner.glob("kanten_*.*"):
        endung = datei.suffix[1:]
        if len(endung) == 2 and endung[0] in "iuf" and endung[1].isdigit():
            laengen[datei.name] = datei.stat().st_size // int(endung[1])
    if len(set(laengen.values())) > 1:
        fehler.append("strassennetz: Kantenspalten verschieden lang: "
                      + ", ".join(f"{k} {v}" for k, v in sorted(laengen.items())))


def pruefen(ordner):
    fehler, hinweise = [], []
    for name in PFLICHT:
        if not (ordner / name).exists():
            fehler.append(f"{name} fehlt")
    for pfad in sorted(ordner.rglob("*")):
        if pfad.is_file() and pfad.stat().st_size == 0:
            fehler.append(f"{pfad.relative_to(ordner)} ist leer")
        if pfad.suffix in (".sqlite", ".mbtiles"):
            datenbank(pfad, fehler, hinweise)
    if (ordner / "strassennetz").is_dir():
        strassennetz(ordner / "strassennetz", fehler)
    return fehler, hinweise


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    fehler, hinweise = pruefen(Path(sys.argv[1]))
    for h in hinweise:
        print(f"  Hinweis: {h}")
    for f in fehler:
        print(f"  FEHLER: {f}")
    if fehler:
        sys.exit(1)
    print("  Prüfung ok")


if __name__ == "__main__":
    main()
