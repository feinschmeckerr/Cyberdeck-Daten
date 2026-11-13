# Cyberdeck-Daten

Offene Kartendaten für die PiFlux-App (iPhone): je Bundesland die Details, die am Pi aus den OSM-Rohdaten entstehen –
Suchindex mit Tippfehler-Wörtern, Straßennetz für die Navigation, Merkmale für die Kombinationssuche, 3D-Gebäude und
Verwaltungsgrenzen (`grenzen.sqlite`: Kreise, Gemeinden, Bezirke, Ortsteile – die Umrisse der Lage-Meldungen, offline).
Die Grundkarten (Vektorkacheln) lädt die App direkt von der Geofabrik. Dazu die Weltkarte als zwei Pakete: `welt`
(Übersicht aus Natural Earth, Zoom 0–7) und `weltosm` (Grundkarte aus OpenStreetMap über VersaTiles, Zoom 0–8).
Außerdem der Fahrplan Berlin/Brandenburg als Paket `oepnv` (VBB-GTFS umgewandelt in `oepnv.sqlite`).

- **Erzeugt** monatlich von `.github/workflows/daten.yml` mit denselben Erzeugern wie am Pi (aus dem privaten Repo
  des PiFlux, nur gelesen). Von Hand: Actions → Daten → Run workflow, auf Wunsch nur einzelne Länder.
  Die Weltkarte schreibt `.github/workflows/welt.yml` nach jedem Daten-Lauf ins aktuelle Release (und von Hand).
  Den Fahrplan schreibt `.github/workflows/oepnv.yml` jeden Montag und nach jedem Daten-Lauf ins aktuelle Release.
- **Probe** der Verwaltungsgrenzen ohne Release: `.github/workflows/grenzen-probe.yml` (nur von Hand, einzelne Länder,
  misst die Größe – veröffentlicht nichts).
- **Ablage:** je Lauf ein Release `daten-JJJJ-MM-TT-N`. Jede Datei einzeln gzip-gepackt (`<land>--<pfad>.gz`, über
  1,9 GB in Teile), dazu je Land ein Manifest `<land>.json` und das Verzeichnis `pakete.json` mit Größen und sha256.
  Die App liest `releases/latest/download/pakete.json`.
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
