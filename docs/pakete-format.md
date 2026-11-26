# Format der Pakete (pakete.json und Dateien)

Die App liest `releases/latest/download/pakete.json`. Fassung des Verzeichnisses: `version` 1 – Neues kommt nur als
zusätzliche Felder bzw. Einträge hinzu, ältere Apps übergehen sie. Zusatzpakete (`lod2-berlin`, `lod2-brandenburg`)
stehen in `laender` mit `art`, `fuer`, `optional` und `lizenz`; sie werden nur auf Wunsch geladen.

## pakete.json

```jsonc
{
 "version": 1,                       // unverändert
 "tag": "daten-2026-11-15-8",
 "erzeugt": "2026-11-15T03:12:00Z",
 "basis": "https://github.com/feinschmeckerr/Cyberdeck-Daten/releases/download/daten-2026-11-15-8/",
 "lizenz": "… © OpenStreetMap … ; 3D-Dächer Berlin … dl-de/zero-2.0 …; 3D-Dächer Brandenburg: © GeoBasis-DE/LGB, dl-de/by-2.0 …",
 "arten": {                          // NEU: was es an Inhalten gibt (Katalog, für neue Apps)
   "gebaeude":  {"name": "3D-Gebäude", "fassung": 3, "inhalt": "Feature-ID (OSM-Kennung*4+Art) und Felder h, m, s, l, u, r, b, rs; eltern bei Gebäudeteilen"},
   "merkmale":  {"name": "Merkmale", "fassung": 2, "inhalt": "Bahnhöfe: level & Co. an Aufzügen und Bahnsteigen, Rolltreppen, …"},
   "geschosse": {"name": "Geschosse (OSM)"},
   "eingaenge": {"name": "Eingänge", "fassung": 2, "inhalt": "zusätzlich ebene, strasse, hausnummer, plz, ort, einheit, breite_m, hoehe_m"},
   "objekt":    {"name": "Objektakte", "fassung": 1, "inhalt": "Einspeisung, Feuermelder, …"},
   "lod2":      {"name": "3D-Dächer (LoD2)", "fassung": 2, "inhalt": "Höfe richtig zerlegt", "optional": true, "nur": ["berlin", "brandenburg"]},
   "suchindex": {...}, "suchwoerter": {...}, "strassennetz": {...}, "grenzen": {...},
   "oepnv": {...}, "welt": {...}, "welt-osm": {...}
 },
 "laender": [ <Manifest>, … ]        // Länder, welt, weltosm, oepnv wie bisher + NEU lod2-berlin, lod2-brandenburg
}
```

Manifest (wie bisher) + optionale neue Felder:

```jsonc
{
 "land": "bremen",                 // bzw. "lod2-berlin"
 "stand": "2026-11-15",
 "groesse": 123, "gz_groesse": 45,
 "dateien": [
  {"pfad": "gebaeude.mbtiles", "groesse": 7524352, "sha256": "…", "gz_groesse": 7012345, "gz_sha256": "…",
   "name": "bremen--gebaeude.mbtiles.gz",
   "art": "gebaeude",              // NEU: erster Pfadteil ohne Endung
   "fassung": 2},                  // NEU, nur wenn die Datei sie nennt (SQLite info.fassung / MBTiles metadata.fassung)
  …
 ],
 // NEU nur bei Zusatzpaketen:
 "art": "lod2", "fuer": "berlin", "optional": true,
 "lizenz": "Senatsverwaltung für Stadtentwicklung, Bauen und Wohnen Berlin: 3D-Gebäudemodelle LoD2, dl-de/zero-2.0 …"
}
```

## Dateien

### gebaeude.mbtiles (Fassung 3; metadata `fassung`=3, `kennung`, `eltern`)
Ebene `gebaeude`, Zoom 14 und 15, wie bisher `h` (Höhe m), `m` (Unterkante), `s`=1 geschätzt, (`f t d a g q` nur mit LoD2 am Pi).
Neu, nur wenn in OSM eingetragen: `l` building:levels, `u` building:levels:underground, `r` roof:levels (Zahl; ganze
Zahlen als int), `b` building=* ohne „yes“ (kurzer Text, nur [a-z0-9_:;.-]), `rs` roof:shape.
**Feature-ID** (MVT-Feld 1): `osm_id*4 + art`, Bit 0 = Relation (sonst Weg), Bit 1 = Gebäudeteil (building:part).
Zurück: `osm = id >> 2`, `relation = id & 1`, `teil = (id >> 1) & 1`. Eindeutig je Kachel und in Z14/Z15 gleich;
< 2^53 (sicher als Double in Ausdrücken). Ein Gebäude an der Landesgrenze kann in zwei Länderpaketen dieselbe ID haben
(je Kachel liefert die App nur eine Datei – unkritisch).
**Fassung 3 – `eltern`** (G-036, nur bei Gebäudeteilen, Bit 1 der Feature-ID gesetzt): ganze Zahl (MVT uint_value) =
Feature-ID des Hauptgebäudes (`osm_id*4 + art`, Bit 1 = 0) – das kleinste Gebäude (building=*, kein Teil), in dem der
Mittelpunkt des Teils liegt (nicht im Hof); gesucht in der Kachel des Teils, sonst in den acht Nachbarkacheln. Fehlt,
wenn kein Gebäude den Teil umschließt. Alle Teile eines Hauses haben denselben Wert; der Umriss des Hauptgebäudes ist
meist nicht in der Kachel (die Teile ersetzen ihn) – steht er doch darin, ist seine Feature-ID gleich `eltern`. In Z14
und Z15 gleich. Ältere Apps übergehen das Feld. metadata `teile_mit_eltern` = Anzahl der Teile mit `eltern`.

### merkmale.sqlite (Fassung 2; info `fassung`=2 – vorher ohne)
Wie bisher (Tabelle `merkmale` mit `typ`, `name`, `breite`, `laenge`, `osm_typ`, `osm_id`, Zellen, `tags` als JSON,
`form`). Seit Fassung 2 ergänzt `werkzeuge/bahnhof.py` nach dem Erzeuger die Angaben für Bahnhöfe (P9 3.1; Tag-Namen
genau wie in OSM, nur wenn eingetragen):
- `highway=elevator`: dazu `level`, `repeat_on`, `level:ref`, `wheelchair:description`, `door`, `width`, `capacity`.
- `railway=platform`: dazu `level`, `layer`, `ref`, `railway:track_ref`, `local_ref`, `height`, `tactile_paving`, `covered`.
- neu `public_transport=platform` (Punkt): Steige, die nicht schon als `railway=platform` oder `highway=bus_stop` im
  Index stehen (Bus- und Trambahnsteige als Linie/Fläche), mit denselben Angaben und den Grundangaben (name, wheelchair,
  route_ref, bus, tram, highway …).
- Rolltreppen: die Stützpunkte von `highway=steps` (Form `linie`) mit `conveying` tragen `conveying`, `level`, `incline`
  (Abfrage der App: `typ = 'highway=steps' AND tags LIKE '%conveying%'`).
- neu `railway=subway_entrance`, `railway=train_station_entrance` (Punkt): `level`, `wheelchair`, `ref`, `name` u. a.
- neu `public_transport=station` (Punkt): Stationen, die nicht schon als `railway=station`/`halt` im Index stehen.
- Ein Objekt mit einer Zeile gleichwertiger Art (Aufzug, der zugleich U-Bahn-Zugang ist) bekommt keine zweite Zeile –
  die Angaben kommen an die vorhandene. Tabellen `typen`/`formen` sind neu gezählt; info `bahnhof` = JSON mit `anzahl`
  und `mit_level` je Art (Rolltreppen je OSM-Weg), `bahnhof_quelle`.

### objekt.sqlite (Fassung 1; info `fassung`=1)
```
objekt(id INTEGER PRIMARY KEY, art TEXT, breite REAL, laenge REAL, zelle INTEGER, name TEXT, ref TEXT, ebene TEXT,
       hoehe_max REAL, breite_max REAL, zugang TEXT, dach INTEGER, details TEXT, form TEXT, west REAL, sued REAL, ost REAL, nord REAL)
objekt_zelle(zelle INTEGER, id INTEGER)          -- INDEX auf zelle; alle Zellen, die der Rahmen berührt (≤ 64)
arten(art TEXT PRIMARY KEY, name TEXT)
info(schluessel TEXT PRIMARY KEY, wert TEXT)       -- erzeugt, quellen, zelle_grad (0.005), fassung, lizenz, anzahl_<art>
```
- `id` = OSM-Kennung*4 + Typ (0 Knoten, 1 Weg). `zelle` = `Int(breite/0.005)*100000 + Int(laenge/0.005)` (wie eingaenge).
- Arten: `einspeisung` (emergency=fire_service_inlet), `feuermelder`, `rettungspunkt` (emergency=access_point, `ref`!),
  `sammelplatz`, `zufahrt` (service=emergency_access / emergency=designated, Linie), `durchfahrt` (tunnel=building_passage,
  Linie, `hoehe_max`/`breite_max` aus maxheight/maxwidth in m), `tiefgarage`, `parkhaus` (amenity=parking + parking=…),
  `einfahrt` (entrance=garage, amenity=parking_entrance), `pv` (power=generator + generator:source=solar; `dach` 1/0/NULL).
- `form`: JSON `[[lon,lat],…]` (6 Stellen, ~1 m vereinfacht) nur bei Wegen von durchfahrt/zufahrt/tiefgarage/parkhaus/sammelplatz.
- `details`: JSON mit kurzen OSM-Werten je Art (z. B. `fire_service_inlet`, `couplings`, `capacity`, `access`, `highway`).
- Abfrage am Umriss: Zellen des Rahmens (mit Rand) → `SELECT o.* FROM objekt_zelle z JOIN objekt o ON o.id=z.id WHERE z.zelle IN (…)`
  (bei mehreren Zellen DISTINCT), dann Punkt im Umriss / nah an der Kante (wie Eingänge) bzw. Linie schneidet Umriss.
- Bewusst NICHT: Schlüsseldepots (emergency=key_depot), Feuerwehrpläne, Personen.

### eingaenge.sqlite (Fassung 2)
Bisher: `id, breite, laenge, art, name, ref, rollstuhl, tuer, zugang, zelle`. Neu hinten: `ebene` (level, Text wie OSM),
`strasse`, `hausnummer`, `plz`, `ort`, `einheit` (addr:*), `breite_m` (width in m), `hoehe_m` (maxheight/height in m, Tore).
`tuer` = door (schon bisher). `ref` bleibt „ref oder Hausnummer“.

### geschosse.sqlite (unverändert, neu im Länderpaket)
`geschosse(id, breite, laenge, geschosse, dach, unter, art, baujahr, zelle)` – wie am Pi.

### lod2.sqlite (Zusatzpaket lod2-<land>, Fassung 2; Blob-Format 1)
```
dach(tx INTEGER, ty INTEGER, daten BLOB, PRIMARY KEY (tx, ty)) WITHOUT ROWID   -- Zoom 15, XYZ (y von Norden)
info(schluessel, wert)   -- land, lizenz, quelle, fassung, format_fassung, zoom (15), extent (4096), gebaeude, dreiecke,
                         -- kacheln, zip_fehler, erzeugt, format
```
`fassung` (info, im Manifest je Datei) ist die Fassung des Inhalts: 1 = erste Pakete (Dächer mit zwei und mehr Höfen
falsch zerlegt), 2 = Höfe richtig zerlegt (G-037). Das Blob-Format (`format_fassung`, Byte nach „LD2“) bleibt 1 – die App
darf die Manifest-Fassung nicht mit dem Blob-Format vergleichen (ein Format > 1 lehnt sie ab).
`daten` = gzip von: `"LD2"`, Format (1 Byte, 1), Anzahl Gebäude (uint32), dann je Gebäude(teil):
`boden` uint16 (dm ü. NHN), `dachform` uint16 (roofType, ALKIS: 1000 Flach, 2100 Pult, 3100 Sattel, 3200 Walm, …; 0 unbekannt),
`n_punkte` uint16, `n_dreiecke` uint16, Punkte `n × (x int16, y int16, z uint16)` – x/y in Kachelpixeln (Extent 4096,
Ursprung oben links, darf über die Kachel hinaus), z in dm über `boden`; Dreiecke `n × 3` Indizes (uint8 wenn
n_punkte ≤ 255, sonst uint16), Umlauf beliebig (doppelseitig zeichnen). Little-endian. Gebäude gehören zur Kachel ihres
Mittelpunkts (wie gebaeude.mbtiles) – für ein gewähltes OSM-Gebäude die Kachel und ihre Nachbarn lesen und die Dächer
nehmen, deren Mittelpunkt im OSM-Umriss liegt. Nur Dachflächen; Wände = Umriss bis Traufe (tiefster Dachpunkt).
Höhe ü. Grund für MapLibre: z/10 (+ evtl. Differenz boden ↔ OSM-Boden ignorieren).
