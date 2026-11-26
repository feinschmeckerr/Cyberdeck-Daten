"""Ergänzt den Merkmal-Index eines Landes (merkmale.sqlite) um die Angaben für Bahnhöfe und Haltestellen (P9 3.1):
Ebenen an Aufzügen und Bahnsteigen, Rolltreppen, Zugänge zu U- und S-Bahn und Stationen.

    python3 werkzeuge/bahnhof.py <merkmale.sqlite> <rohdaten.osm.pbf> [weitere.osm.pbf …]

Läuft nach dem Erzeuger des PiFlux (merkmale-erzeugen.py) auf dessen Ergebnis und liest die OSM-Rohdaten ein zweites
Mal, nur nach den Schlüsseln highway, railway und public_transport. Die Datei bleibt im selben Format (Tabelle
merkmale, Spalte tags als JSON); ältere Apps übergehen, was sie nicht kennen. Neu bzw. ergänzt (Tag-Namen wie in OSM):

- highway=elevator (Punkt): zusätzlich level, repeat_on, level:ref, wheelchair:description, door, width, capacity
- railway=platform (Punkt): zusätzlich level, layer, ref, railway:track_ref, local_ref, height, tactile_paving, covered
- public_transport=platform (neue Art, Punkt): Bahnsteige und Steige, die nicht schon als railway=platform oder
  highway=bus_stop im Index stehen (Tram- und Bussteige als Fläche oder Linie), mit denselben Angaben
- highway=steps mit conveying (Rolltreppe): die Stützpunkte der Treppe (Form „linie“) tragen conveying, level,
  incline – die App findet sie über „tags LIKE '%conveying%'“
- railway=subway_entrance, railway=train_station_entrance (neue Arten, Punkt): level, wheelchair, ref, name …
- public_transport=station (neue Art, Punkt): Stationen, die nicht schon als railway=station/halt im Index stehen

Ein Objekt, das schon einen Punkt der gleichwertigen Art hat (ein Aufzug, der zugleich U-Bahn-Zugang ist; ein Bahnsteig
mit railway=platform und public_transport=platform), bekommt keine zweite Zeile – seine Zeile bekommt die Angaben dazu.
Sonst gilt wie im Erzeuger: Lage = Mittel der Knoten eines Wegs. Quelle: OpenStreetMap (ODbL).
info: fassung = 2 (ohne: ohne diese Angaben), bahnhof = JSON mit Anzahl und „mit_level“ je Art.
"""

import json
import math
import sqlite3
import sys
import time
from pathlib import Path

FASSUNG = 2
ZELLE_GRAD = 0.01  # wie im Index (info.zelle_grad); wird aus der Datei gelesen

AUFZUG = ("level", "repeat_on", "level:ref", "wheelchair:description", "door", "width", "capacity")
BAHNSTEIG = ("level", "layer", "ref", "railway:track_ref", "local_ref", "height", "tactile_paving", "covered")
ROLLTREPPE = ("conveying", "level", "incline")
ZUGANG = ("level", "wheelchair", "ref", "name")
# Grundangaben neuer Zeilen (wie die Eigenschaften im Index: was die App für Halt und Bahnhof liest)
GRUND = ("name", "name:de", "wheelchair", "operator", "network", "description", "route_ref", "access", "shelter",
         "bench", "bus", "tram", "train", "subway", "light_rail", "highway", "railway", "public_transport", "entrance",
         "ref", "website", "wikidata")
ROLLTREPPE_WERTE = {"yes", "forward", "backward", "reversible"}

NEUE_ARTEN = ("public_transport=platform", "railway=subway_entrance", "railway=train_station_entrance",
              "public_transport=station")


def auswahl(tags, schluessel):
    """Die genannten Tags, soweit eingetragen (leere Werte fallen weg)."""
    return {k: tags[k] for k in schluessel if tags.get(k, "").strip()}


def arten(tags):
    """Was ein OSM-Objekt für den Bahnhof ist: Liste der Arten (Typ im Index) mit den Angaben, die dazugehören."""
    ergebnis = []
    highway, railway, pt = tags.get("highway"), tags.get("railway"), tags.get("public_transport")
    if highway == "elevator":
        ergebnis.append(("highway=elevator", AUFZUG))
    if railway == "platform" or pt == "platform":
        ergebnis.append(("railway=platform" if railway == "platform" else "public_transport=platform", BAHNSTEIG))
    if highway == "steps" and tags.get("conveying") in ROLLTREPPE_WERTE:
        ergebnis.append(("highway=steps", ROLLTREPPE))
    if railway in ("subway_entrance", "train_station_entrance"):
        ergebnis.append((f"railway={railway}", ZUGANG))
    if pt == "station":
        ergebnis.append(("public_transport=station", ()))
    return ergebnis


# Wo eine neue Art keine eigene Zeile bekommt, weil das Objekt schon unter einer gleichwertigen Art steht
GLEICHWERTIG = {
    "public_transport=platform": ("railway=platform", "highway=bus_stop"),
    "railway=subway_entrance": ("highway=elevator",),
    "railway=train_station_entrance": ("highway=elevator",),
    "public_transport=station": ("railway=station", "railway=halt"),
}


def mitte_linie(punkte):
    """Mitte entlang einer Linie [(breite, länge) …] (eben genähert)."""
    if len(punkte) == 1:
        return punkte[0]
    k = math.cos(math.radians(punkte[0][0]))
    stuecke = [math.hypot(b2 - b1, (l2 - l1) * k) for (b1, l1), (b2, l2) in zip(punkte, punkte[1:])]
    halb, weg = sum(stuecke) / 2, 0.0
    for (a, z), s in zip(zip(punkte, punkte[1:]), stuecke):
        if weg + s >= halb and s > 0:
            t = (halb - weg) / s
            return a[0] + (z[0] - a[0]) * t, a[1] + (z[1] - a[1]) * t
        weg += s
    return punkte[len(punkte) // 2]


class Ergaenzung:
    """Sammelt die Angaben aus OSM und schreibt sie in den Index (getrennt vom Lesen, damit es ohne pyosmium prüfbar ist)."""

    def __init__(self, db):
        self.db = db
        self.zelle = float((db.execute("SELECT wert FROM info WHERE schluessel = 'zelle_grad'").fetchone() or [ZELLE_GRAD])[0])
        # bestehende Zeilen der betroffenen Arten: (osm_typ, osm_id, typ) → [(rowid, tags)]
        self.zeilen = {}
        for rowid, typ, osm_typ, osm_id, tags in db.execute(
                "SELECT id, typ, osm_typ, osm_id, tags FROM merkmale WHERE typ IN "
                "('highway=elevator', 'railway=platform', 'highway=bus_stop', 'railway=station', 'railway=halt', "
                "'highway=steps', 'public_transport=platform', 'railway=subway_entrance', "
                "'railway=train_station_entrance', 'public_transport=station')"):
            self.zeilen.setdefault((osm_typ, osm_id, typ), []).append((rowid, tags))
        self.geaendert = {}   # rowid → tags (dict)
        self.neu = {}         # (osm_typ, osm_id, typ) → Zeile
        self.zahlen = {}

    def _mischen(self, rowid, alt, extra):
        tags = self.geaendert.get(rowid)
        if tags is None:
            tags = json.loads(alt) if alt else {}
        neu = {k: v for k, v in extra.items() if k not in tags}
        if neu:
            tags.update(neu)
            self.geaendert[rowid] = tags

    def objekt(self, osm_typ, osm_id, tags, lage, linie=None):
        """Ein OSM-Objekt (tags als dict, lage = (breite, länge) wie im Erzeuger, linie = Punkte des Wegs)."""
        for typ, schluessel in arten(tags):
            extra = auswahl(tags, schluessel)
            bestehend = self.zeilen.get((osm_typ, osm_id, typ), [])
            if not bestehend:
                for andere in GLEICHWERTIG.get(typ, ()):
                    if (osm_typ, osm_id, andere) in self.zeilen:
                        # Bushalt bleibt Bushalt (die App liest ihn als Halt, nicht als Bahnsteig) – keine neue Zeile
                        bestehend = self.zeilen[(osm_typ, osm_id, andere)]
                        if andere == "highway=bus_stop":
                            extra = {}
                        break
            for rowid, alt in bestehend:
                if extra:
                    self._mischen(rowid, alt, extra)
            if bestehend:
                continue
            if typ == "highway=steps":
                if linie:  # Treppe ohne Stützpunkt im Index: einer in der Mitte
                    self._neu(osm_typ, osm_id, typ, tags, extra, mitte_linie(linie), "linie", knapp=True)
            elif typ in NEUE_ARTEN and lage:
                # Aufzüge und railway=platform stehen schon im Index (sonst unter einer anderen Art) – nur ergänzen
                self._neu(osm_typ, osm_id, typ, tags, extra, lage, "punkt")

    def _neu(self, osm_typ, osm_id, typ, tags, extra, lage, form, knapp=False):
        schluessel = (osm_typ, osm_id, typ)
        if schluessel in self.neu:
            return  # schon aus dem Nachbarland (Berlin in Brandenburg)
        werte = dict(extra) if knapp else {**auswahl(tags, GRUND), **extra}
        if knapp and tags.get("ref"):
            werte["ref"] = tags["ref"]
        breite, laenge = lage
        name = tags.get("name:de") or tags.get("name") or ""
        self.neu[schluessel] = (typ, name, round(breite, 6), round(laenge, 6), osm_typ, osm_id,
                                int(breite // self.zelle), int(laenge // self.zelle),
                                json.dumps(werte, ensure_ascii=False, separators=(",", ":")) if werte else None, form)

    def schreiben(self):
        """Änderungen in die Datei, Tabellen typen/formen neu, Zeilen wie im Erzeuger nach Art und Zelle geordnet."""
        db = self.db
        db.executemany("UPDATE merkmale SET tags = ? WHERE id = ?",
                       [(json.dumps(t, ensure_ascii=False, separators=(",", ":")), rowid) for rowid, t in self.geaendert.items()])
        db.executemany("INSERT INTO merkmale (typ, name, breite, laenge, osm_typ, osm_id, zelle_lat, zelle_lon, tags, form) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", list(self.neu.values()))
        if self.neu:
            # wie nach_art_ordnen im Erzeuger: die Zeilen einer Art beieinander (wenige Seiten je Abfrage)
            sql = db.execute("SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'merkmale'").fetchone()[0]
            spalten = "typ, name, breite, laenge, osm_typ, osm_id, zelle_lat, zelle_lon, tags, form"
            indizes = [z[0] for z in db.execute("SELECT sql FROM sqlite_schema WHERE type = 'index' AND tbl_name = 'merkmale' "
                                                "AND sql IS NOT NULL")]
            db.execute(sql.replace("CREATE TABLE \"merkmale\"", "CREATE TABLE merkmale_sortiert", 1)
                       .replace("CREATE TABLE merkmale", "CREATE TABLE merkmale_sortiert", 1))
            db.execute(f"INSERT INTO merkmale_sortiert ({spalten}) SELECT {spalten} FROM merkmale "
                       "ORDER BY typ, zelle_lat, zelle_lon, id")
            db.execute("DROP TABLE merkmale")
            db.execute("ALTER TABLE merkmale_sortiert RENAME TO merkmale")
            for sql in indizes:
                db.execute(sql)
        for tabelle, abfrage in (("typen", "SELECT typ, COUNT(*) AS anzahl FROM merkmale GROUP BY typ"),
                                 ("formen", "SELECT typ, form, COUNT(*) AS anzahl FROM merkmale GROUP BY typ, form")):
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name = ?", (tabelle,)).fetchone():
                db.execute(f"DROP TABLE {tabelle}")
                db.execute(f"CREATE TABLE {tabelle} AS {abfrage}")
        self.zahlen = abdeckung(db)
        db.execute("DELETE FROM info WHERE schluessel IN ('fassung', 'bahnhof', 'bahnhof_quelle')")
        db.executemany("INSERT INTO info VALUES (?, ?)", [
            ("fassung", str(FASSUNG)),
            ("bahnhof", json.dumps(self.zahlen, ensure_ascii=False, separators=(",", ":"))),
            ("bahnhof_quelle", "© OpenStreetMap-Mitwirkende (ODbL); werkzeuge/bahnhof.py " + time.strftime("%Y-%m-%d"))])
        db.commit()


def abdeckung(db):
    """Zahlen je Art im Index: alle, mit level (bzw. repeat_on), bei Treppen die Rolltreppen (je OSM-Objekt einmal)."""
    zahlen = {}
    for typ in ("highway=elevator", "railway=platform") + NEUE_ARTEN:
        alle, mit = db.execute(
            "SELECT COUNT(*), COUNT(json_extract(tags, '$.level')) + "
            "SUM(json_extract(tags, '$.level') IS NULL AND json_extract(tags, '$.repeat_on') IS NOT NULL) "
            "FROM merkmale WHERE typ = ? AND form = 'punkt'", (typ,)).fetchone()
        zahlen[typ] = {"anzahl": alle, "mit_level": mit or 0}
    alle, mit = db.execute(
        "SELECT COUNT(*), COUNT(level) FROM (SELECT osm_id, MAX(json_extract(tags, '$.level')) AS level FROM merkmale "
        "WHERE typ = 'highway=steps' AND json_extract(tags, '$.conveying') IS NOT NULL GROUP BY osm_typ, osm_id)").fetchone()
    zahlen["rolltreppe"] = {"anzahl": alle, "mit_level": mit}
    return zahlen


def lesen(ergaenzung, datei):
    import osmium  # nur beim Lesen der Rohdaten nötig (die Tests kommen ohne aus)

    class Leser(osmium.SimpleHandler):
        def node(self, n):
            if n.location.valid():
                ergaenzung.objekt("n", n.id, {t.k: t.v for t in n.tags}, (n.location.lat, n.location.lon))

        def way(self, w):
            punkte = [(k.location.lat, k.location.lon) for k in w.nodes if k.location.valid()]
            if punkte:
                # Lage wie im Erzeuger: Mittel aller Knoten (bei Flächen zählt der Schlusspunkt doppelt)
                lage = (sum(p[0] for p in punkte) / len(punkte), sum(p[1] for p in punkte) / len(punkte))
                ergaenzung.objekt("w", w.id, {t.k: t.v for t in w.tags}, lage, punkte)

    # nur Objekte mit diesen Schlüsseln kommen in Python an; die Lage der Knoten kennt der Index trotzdem
    Leser().apply_file(str(datei), locations=True, idx="flex_mem",
                       filters=[osmium.filter.KeyFilter("highway", "railway", "public_transport")])


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    ziel, dateien = Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]]
    beginn = time.time()
    vorher = ziel.stat().st_size
    db = sqlite3.connect(ziel)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    ergaenzung = Ergaenzung(db)
    for datei in dateien:
        print(f"lese {datei.name} …", flush=True)
        lesen(ergaenzung, datei)
    ergaenzung.schreiben()
    db.execute("VACUUM")
    db.close()
    print(f"  {len(ergaenzung.geaendert):,} Zeilen ergänzt, {len(ergaenzung.neu):,} neu "
          f"({', '.join(f'{t} {sum(1 for k in ergaenzung.neu if k[2] == t):,}' for t in NEUE_ARTEN + ('highway=steps',))})")
    for typ, z in ergaenzung.zahlen.items():
        print(f"  {typ}: {z['anzahl']:,}, mit level {z['mit_level']:,}")
    print(f"fertig in {time.time() - beginn:.0f} s: {vorher / 1e6:.1f} MB → {ziel.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
