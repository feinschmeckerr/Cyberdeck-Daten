# Cyberdeck-Daten

Offene Kartendaten für die PiFlux-App (iPhone): je Bundesland die Details, die am Pi aus den OSM-Rohdaten entstehen –
Suchindex mit Tippfehler-Wörtern, Straßennetz für die Navigation, Merkmale für die Kombinationssuche, 3D-Gebäude und
Verwaltungsgrenzen (`grenzen.sqlite`: Kreise, Gemeinden, Bezirke, Ortsteile – die Umrisse der Lage-Meldungen, offline).
Die Grundkarten (Vektorkacheln) lädt die App direkt von der Geofabrik. Dazu die Weltkarte als zwei Pakete: `welt`
(Übersicht aus Natural Earth, Zoom 0–7) und `weltosm` (Grundkarte aus OpenStreetMap über VersaTiles, Zoom 0–8).
Außerdem der Fahrplan Berlin/Brandenburg als Paket `oepnv` (VBB-GTFS umgewandelt in `oepnv.sqlite`).
Für die Objektakte je Land zusätzlich `geschosse.sqlite`, `eingaenge.sqlite` und `objekt.sqlite` (Feuerwehr-Einspeisung,
Durchfahrten mit Höhe, Tiefgaragen, Rettungspunkte …), die 3D-Gebäude mit Feature-ID; für Berlin und Brandenburg die
Zusatzpakete `lod2-berlin` und `lod2-brandenburg` (vereinfachte 3D-Dächer, nur auf Wunsch). Format: `docs/pakete-format.md`.

- **Erzeugt** monatlich von `.github/workflows/daten.yml` mit denselben Erzeugern wie am Pi (aus dem privaten Repo
  des PiFlux, nur gelesen). Von Hand: Actions → Daten → Run workflow, auf Wunsch nur einzelne Länder.
  Die Weltkarte schreibt `.github/workflows/welt.yml` nach jedem Daten-Lauf ins aktuelle Release (und von Hand).
  Den Fahrplan schreibt `.github/workflows/oepnv.yml` jeden Montag und nach jedem Daten-Lauf ins aktuelle Release.
- **3D-Dächer** schreibt `.github/workflows/lod2.yml` (von Hand bzw. vierteljährlich neu; nach jedem Daten-Lauf übernimmt
  es die Pakete ins neue Release).
- **Probe** der Verwaltungsgrenzen ohne Release: `.github/workflows/grenzen-probe.yml` (nur von Hand, einzelne Länder,
  misst die Größe – veröffentlicht nichts).
- **Ablage:** je Lauf ein Release `daten-JJJJ-MM-TT-N`. Jede Datei einzeln gzip-gepackt (`<land>--<pfad>.gz`, über
  1,9 GB in Teile), dazu je Land ein Manifest `<land>.json` und das Verzeichnis `pakete.json` mit Größen und sha256.
  Die App liest `releases/latest/download/pakete.json`. Ein neues Release wird erst „latest“, wenn alle Länder fertig
  sind und Welt, Fahrplan und 3D-Dächer aus dem bisherigen Release mitgenommen wurden (`werkzeuge/mitnehmen.py`);
  Welt und Fahrplan erzeugen danach wie bisher neu.
- **Hier liegt nur Offenes,** nie eigene Daten (Wegpunkte, Missionen, Schlüssel).

## Lizenz der Daten

© OpenStreetMap-Mitwirkende, verfügbar unter der [Open Database License 1.0](https://www.openstreetmap.org/copyright),
bezogen über die [Geofabrik](https://download.geofabrik.de) und [VersaTiles](https://versatiles.org). Die Daten sind
abgeleitete Datenbanken im Sinne der ODbL und stehen unter derselben Lizenz. Die Welt-Übersicht stammt aus
[Natural Earth](https://www.naturalearthdata.com) (gemeinfrei).

Die Verwaltungsgrenzen der Kreise und Gemeinden (`grenzen.sqlite`, Ebene 6 und 8): © GeoBasis-DE / BKG (VG250),
[Datenlizenz Deutschland – Namensnennung – 2.0](https://www.govdata.de/dl-de/by-2-0), vereinfacht. Bezirke und
Ortsteile (Ebene 9 und 10) stammen aus OpenStreetMap (ODbL, s. o.). Der Vermerk steht auch in der Datei (Tabelle `lizenz`).

Der Fahrplan (`oepnv`): © VBB Verkehrsverbund Berlin-Brandenburg GmbH, GTFS-Daten unter
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) ([vbb.de/vbbgtfs](https://www.vbb.de/vbbgtfs)), umgewandelt.

Die 3D-Dächer (`lod2-berlin`, `lod2-brandenburg`, vereinfacht): Berlin – Senatsverwaltung für Stadtentwicklung, Bauen und
Wohnen, 3D-Gebäudemodelle LoD2, [Datenlizenz Deutschland – Zero – 2.0](https://www.govdata.de/dl-de/zero-2-0);
Brandenburg – **© GeoBasis-DE/LGB**, [Datenlizenz Deutschland – Namensnennung – 2.0](https://www.govdata.de/dl-de/by-2-0).
Der Vermerk steht auch in der Datei (Tabelle `info`, Schlüssel `lizenz`) und im Manifest (`lizenz`).
