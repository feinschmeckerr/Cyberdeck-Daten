"""Gebäudeteile genauer (gebaeude.mbtiles Fassung 4, P9 3.3): ergänzt an jedem Gebäudeteil (building:part, Bit 1 der
Feature-ID) die Felder

    bp  building:part=* ohne „yes“ (roof, platform, tower …; kurzer Text, nur [a-z0-9_:;.-])
    ml  min_level, xl max_level (Etagen-Nummern wie level; Zahl, ganze Zahlen als int, negative als sint) –
        fehlen beide, ersatzweise aus level des Teils („-2;-1“ → ml −2, xl −1)
    ly  layer (ganze Zahl, −10 … 10)

    python3 werkzeuge/gebaeudeteile.py <gebaeude.mbtiles> <rohdaten.osm.pbf> [weitere.osm.pbf …]

Läuft nach dem Erzeuger des PiFlux (gebaeude-erzeugen.py, Fassung 3) auf dessen Ergebnis: liest aus den OSM-Rohdaten nur
die Tags der Wege und Multipolygon-Relationen mit building:part (ohne Knoten, schnell) und schreibt die Felder in die
Kacheln (Zoom 14 und 15) dazu. Geometrie, Feature-ID und die bisherigen Felder (h, m, s, l, u, r, b, rs, eltern,
LoD2-Felder) bleiben unverändert; roof:shape des Teils steht schon in rs. Ältere Apps übergehen die neuen Felder.
metadata: fassung 4 (nur aus 3), teile_mit_bp, teile_mit_ebene (ml oder xl), teile_mit_layer, json (Felder).
Quelle: OpenStreetMap (ODbL).
"""

import gzip
import json
import re
import sqlite3
import struct
import sys
import time
from pathlib import Path

FASSUNG_VORHER, FASSUNG = 3, 4
NEUE_FELDER = {"bp": "String", "ml": "Number", "xl": "Number", "ly": "Number"}
_ARTWERT = re.compile(r"^[a-z0-9_:;.-]{1,24}$")
_ZAHL = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*$")


# ---------- Werte aus OSM ----------

def zahl(text, unten, oben):
    """„-1“, „2,5“ → Zahl in [unten, oben] (ganze Zahlen als int) oder None."""
    treffer = _ZAHL.match(text or "")
    if not treffer:
        return None
    wert = float(treffer.group(1).replace(",", "."))
    if not unten <= wert <= oben:
        return None
    return int(wert) if wert == int(wert) else round(wert, 1)


def ebenen(level):
    """Etagen aus level: „-1;0“ → [−1, 0], „0-2“ → [0, 1, 2], „-2--1“ → [−2, −1]; Unsinn fällt weg."""
    menge = set()
    for teil in re.split(r"[;,]", level or ""):
        teil = teil.strip()
        bereich = re.match(r"^(-?\d+)-(-?\d+)$", teil)
        if bereich:
            von, bis = int(bereich.group(1)), int(bereich.group(2))
            if von <= bis and bis - von <= 20:
                menge.update(range(von, bis + 1))
        elif (n := zahl(teil, -20, 200)) is not None:
            menge.add(n)
    return sorted(menge)


def ist_teil(tags):
    """Wie im Erzeuger: building:part (nicht „no“) ohne building=* – nur diese tragen Bit 1 in der Feature-ID."""
    teil, art = tags.get("building:part"), tags.get("building")
    return bool(teil and teil != "no" and not art)


def felder(tags):
    """Neue Felder eines Gebäudeteils aus seinen Tags (dict) – nur, was eingetragen ist."""
    ergebnis = {}
    art = (tags.get("building:part") or "").strip().lower()
    if art and art not in ("yes", "no") and _ARTWERT.match(art):
        ergebnis["bp"] = art
    ml, xl = zahl(tags.get("min_level"), -20, 200), zahl(tags.get("max_level"), -20, 200)
    if ml is None and xl is None and (stufen := ebenen(tags.get("level"))):
        ml, xl = stufen[0], stufen[-1]
    if ml is not None:
        ergebnis["ml"] = ml
    if xl is not None:
        ergebnis["xl"] = xl
    ly = zahl(tags.get("layer"), -10, 10)
    if isinstance(ly, int):
        ergebnis["ly"] = ly
    return ergebnis


def kennung(osm_id, relation):
    """Feature-ID eines Gebäudeteils wie im Erzeuger: OSM-Kennung × 4 + 2 (Teil) + 1 bei Relation."""
    return osm_id * 4 + 2 + (1 if relation else 0)


# ---------- Protobuf (Mapbox Vector Tile) ----------

def _varint(n):
    teile = bytearray()
    while n > 0x7F:
        teile.append(n & 0x7F | 0x80)
        n >>= 7
    teile.append(n)
    return bytes(teile)


def _lies_varint(daten, i):
    n = verschiebung = 0
    while True:
        b = daten[i]
        i += 1
        n |= (b & 0x7F) << verschiebung
        if b < 0x80:
            return n, i
        verschiebung += 7


def felder_lesen(daten):
    """[(nummer, drahttyp, wert, roh)] – wert: Zahl (Typ 0) bzw. Bytes; roh: das ganze Feld (zum unveränderten Schreiben)."""
    ergebnis, i = [], 0
    while i < len(daten):
        anfang = i
        kopf, i = _lies_varint(daten, i)
        nummer, typ = kopf >> 3, kopf & 7
        if typ == 0:
            wert, i = _lies_varint(daten, i)
        elif typ == 1:
            wert, i = daten[i:i + 8], i + 8
        elif typ == 2:
            laenge, i = _lies_varint(daten, i)
            wert, i = daten[i:i + laenge], i + laenge
        elif typ == 5:
            wert, i = daten[i:i + 4], i + 4
        else:
            raise ValueError(f"Drahttyp {typ} unbekannt")
        ergebnis.append((nummer, typ, wert, daten[anfang:i]))
    return ergebnis


def _laenge(nummer, daten):
    return _varint(nummer << 3 | 2) + _varint(len(daten)) + daten


def wert_lesen(daten):
    """MVT-Value → (Art, Wert) zum Vergleichen: ('s', text), ('i', ganz), ('f', zahl), ('b', wahr)."""
    for nummer, _typ, wert, _roh in felder_lesen(daten):
        if nummer == 1:
            return "s", bytes(wert).decode()
        if nummer == 2:
            return "f", struct.unpack("<f", wert)[0]
        if nummer == 3:
            return "f", struct.unpack("<d", wert)[0]
        if nummer in (4, 5):
            return "i", wert if wert < 1 << 63 else wert - (1 << 64)
        if nummer == 6:
            return "i", (wert >> 1) ^ -(wert & 1)
        if nummer == 7:
            return "b", bool(wert)
    return None


def wert_schluessel(wert):
    if isinstance(wert, str):
        return "s", wert
    if isinstance(wert, int):
        return "i", wert
    return "f", float(wert)


def wert_schreiben(wert):
    """Text als string_value, ganze Zahl ≥ 0 als uint_value (wie der Erzeuger), < 0 als sint_value, sonst double."""
    if isinstance(wert, str):
        return _laenge(1, wert.encode())
    if isinstance(wert, int):
        if wert >= 0:
            return _varint(5 << 3) + _varint(wert)
        return _varint(6 << 3) + _varint((wert << 1) ^ (wert >> 63))
    return _varint(3 << 3 | 1) + struct.pack("<d", float(wert))


def ebene_ergaenzen(ebene, teile):
    """Eine MVT-Ebene (Bytes) mit den Feldern der Teile (Feature-ID → {feld: wert}) ergänzen.
    Gibt (neue Bytes, Feature-IDs der ergänzten Objekte) zurück; ein Feld, das ein Objekt schon hat, bleibt."""
    teile_der_ebene = felder_lesen(ebene)
    schluessel = [bytes(w).decode() for n, _t, w, _r in teile_der_ebene if n == 3]
    werte = [wert_lesen(w) for n, _t, w, _r in teile_der_ebene if n == 4]
    schluessel_nr = {k: i for i, k in enumerate(schluessel)}
    wert_nr = {}
    for i, w in enumerate(werte):
        wert_nr.setdefault(w, i)
    neue_schluessel, neue_werte, objekte, ergaenzt = [], [], [], set()
    for nummer, _typ, wert, roh in teile_der_ebene:
        if nummer != 2:
            continue
        objekt = felder_lesen(wert)
        fid = next((w for n, _t, w, _r in objekt if n == 1), None)
        dazu = teile.get(fid) if fid is not None and fid >> 1 & 1 else None
        if not dazu:
            objekte.append(roh)
            continue
        tag_feld = next((w for n, t, w, _r in objekt if n == 2 and t == 2), b"")
        tags, i = [], 0
        while i < len(tag_feld):
            n, i = _lies_varint(tag_feld, i)
            tags.append(n)
        vorhanden = {schluessel[k] for k in tags[0::2]}
        neu = False
        for feld, w in dazu.items():
            if feld in vorhanden:
                continue
            if feld not in schluessel_nr:
                schluessel_nr[feld] = len(schluessel) + len(neue_schluessel)
                neue_schluessel.append(feld)
            ws = wert_schluessel(w)
            if ws not in wert_nr:
                wert_nr[ws] = len(werte) + len(neue_werte)
                neue_werte.append(w)
            tags += [schluessel_nr[feld], wert_nr[ws]]
            neu = True
        if not neu:
            objekte.append(roh)
            continue
        ergaenzt.add(fid)
        neues_objekt = b""
        tags_geschrieben = False
        for n, t, w, r in objekt:
            if n == 2 and t == 2:
                neues_objekt += _laenge(2, b"".join(_varint(x) for x in tags))
                tags_geschrieben = True
            else:
                neues_objekt += bytes(r)
        if not tags_geschrieben:
            neues_objekt += _laenge(2, b"".join(_varint(x) for x in tags))
        objekte.append(_laenge(2, neues_objekt))
    if not ergaenzt:
        return ebene, ergaenzt
    # Reihenfolge wie im Erzeuger: Fassung, Name, Objekte, Schlüssel, Werte, Extent (dann Unbekanntes)
    vorn = b"".join(bytes(r) for n, _t, _w, r in teile_der_ebene if n in (15, 1))
    hinten = b"".join(bytes(r) for n, _t, _w, r in teile_der_ebene if n not in (15, 1, 2, 3, 4))
    alte_schluessel = b"".join(bytes(r) for n, _t, _w, r in teile_der_ebene if n == 3)
    alte_werte = b"".join(bytes(r) for n, _t, _w, r in teile_der_ebene if n == 4)
    return (vorn + b"".join(bytes(o) for o in objekte) + alte_schluessel
            + b"".join(_laenge(3, k.encode()) for k in neue_schluessel)
            + alte_werte + b"".join(_laenge(4, wert_schreiben(w)) for w in neue_werte) + hinten), ergaenzt


def kachel_ergaenzen(daten, teile):
    """Ganze Kachel (ungepackt) → (neue Bytes, Feature-IDs der ergänzten Objekte)."""
    ergebnis, ergaenzt = b"", set()
    for nummer, _typ, wert, roh in felder_lesen(daten):
        if nummer == 3:
            neu, ids = ebene_ergaenzen(bytes(wert), teile)
            ergaenzt |= ids
            ergebnis += _laenge(3, neu) if ids else bytes(roh)
        else:
            ergebnis += bytes(roh)
    return ergebnis, ergaenzt


# ---------- OSM lesen und Datei schreiben ----------

def lesen(datei, teile):
    import osmium  # nur beim Lesen der Rohdaten nötig (die Tests kommen ohne aus)

    class Leser(osmium.SimpleHandler):
        def way(self, w):
            tags = {t.k: t.v for t in w.tags}
            if ist_teil(tags) and (f := felder(tags)):
                teile.setdefault(kennung(w.id, False), f)

        def relation(self, r):
            tags = {t.k: t.v for t in r.tags}
            if tags.get("type") == "multipolygon" and ist_teil(tags) and (f := felder(tags)):
                teile.setdefault(kennung(r.id, True), f)

    Leser().apply_file(str(datei), filters=[osmium.filter.KeyFilter("building:part")])


def ergaenzen(ziel, teile):
    """Kacheln der Datei ergänzen und Metadaten setzen; gibt die Zahlen zurück."""
    db = sqlite3.connect(ziel)
    db.execute("PRAGMA journal_mode=OFF")
    meta = dict(db.execute("SELECT name, value FROM metadata"))
    fassung = int(meta.get("fassung") or 0)
    if fassung >= FASSUNG:
        db.close()
        sys.exit(f"{ziel} hat schon Fassung {fassung}")
    zahlen = {"kacheln": 0, "objekte": 0}
    aenderungen, in_kacheln = [], set()
    for z, x, y, daten in db.execute("SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles"):
        roh = gzip.decompress(daten) if daten[:2] == b"\x1f\x8b" else daten
        neu, ids = kachel_ergaenzen(roh, teile)
        if ids:
            aenderungen.append((gzip.compress(neu, 6), z, x, y))
            zahlen["kacheln"] += 1
            zahlen["objekte"] += len(ids)
            in_kacheln |= ids
    db.executemany("UPDATE tiles SET tile_data = ? WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?", aenderungen)
    # je Teil in den Kacheln einmal gezählt (in Zoom 14 und 15 steht er doppelt)
    zahlen["teile_mit_bp"] = sum(1 for k in in_kacheln if "bp" in teile[k])
    zahlen["teile_mit_ebene"] = sum(1 for k in in_kacheln if "ml" in teile[k] or "xl" in teile[k])
    zahlen["teile_mit_layer"] = sum(1 for k in in_kacheln if "ly" in teile[k])
    try:
        beschreibung = json.loads(meta.get("json") or "{}")
        for ebene in beschreibung.get("vector_layers", []):
            ebene.setdefault("fields", {}).update(NEUE_FELDER)
    except ValueError:
        beschreibung = None
    neu_meta = {"teile_mit_bp": str(zahlen["teile_mit_bp"]), "teile_mit_ebene": str(zahlen["teile_mit_ebene"]),
                "teile_mit_layer": str(zahlen["teile_mit_layer"]),
                "teile": "bp building:part, ml/xl min_level/max_level (sonst aus level), ly layer"}
    if fassung == FASSUNG_VORHER:
        neu_meta["fassung"] = str(FASSUNG)
    else:
        print(f"  Achtung: Fassung {fassung} statt {FASSUNG_VORHER} – Felder ergänzt, Fassung bleibt", flush=True)
    if beschreibung is not None:
        neu_meta["json"] = json.dumps(beschreibung)
    for name, wert in neu_meta.items():
        db.execute("DELETE FROM metadata WHERE name = ?", (name,))
        db.execute("INSERT INTO metadata VALUES (?, ?)", (name, wert))
    db.commit()
    db.execute("VACUUM")
    db.close()
    return zahlen


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    ziel, dateien = Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]]
    beginn, vorher = time.time(), ziel.stat().st_size
    teile = {}
    for datei in dateien:
        print(f"lese {datei.name} …", flush=True)
        lesen(datei, teile)
    print(f"  {len(teile):,} Gebäudeteile mit neuen Angaben ({time.time() - beginn:.0f} s)", flush=True)
    zahlen = ergaenzen(ziel, teile)
    print(f"  {zahlen['objekte']:,} Objekte in {zahlen['kacheln']:,} Kacheln ergänzt (Zoom 14 und 15); Teile mit bp "
          f"{zahlen['teile_mit_bp']:,}, mit ml/xl {zahlen['teile_mit_ebene']:,}, mit ly {zahlen['teile_mit_layer']:,}")
    print(f"fertig in {time.time() - beginn:.0f} s: {vorher / 1e6:.1f} MB → {ziel.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
