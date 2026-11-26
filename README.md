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

- **Ablage:** je Lauf ein Release `daten-JJJJ-MM-TT-N`. Jede Datei einzeln gzip-gepackt (`<land>--<pfad>.gz`, über
  1,9 GB in Teile), dazu je Paket ein Manifest `<land>.json` und das Verzeichnis `pakete.json` mit Größen und sha256.
  Die App liest `releases/latest/download/pakete.json`. Ein neues Release wird erst „latest“, wenn alle 16 Länder,
  Welt und Fahrplan darin stehen – was ein Lauf nicht neu gebaut hat, nimmt `werkzeuge/mitnehmen.py` mit Prüfsummen
  aus dem bisherigen Release mit.
- **Hier liegt nur Offenes,** nie eigene Daten (Wegpunkte, Missionen, Schlüssel).

## Lauf auf dem Mac

Die Pakete entstehen auf dem Mac – GitHub Actions nutzt dieses Repo nicht mehr (die früheren Workflows stehen in der
Git-Geschichte). Zwei Skripte:

- `werkzeuge/daten-lauf.sh` baut die Pakete in einen Ausgabeordner (Standard `~/Cyberdeck-Daten-Lauf`): OSM-Rohdaten
  von der Geofabrik (fällt sie aus: Deutschland-Auszug von openstreetmap.fr, an der Landesgrenze geschnitten), dann die
  Erzeuger des App-Repos Cyberdeck (derselbe Code wie am Pi – er läuft aus einer Kopie des Zweigs, im App-Repo ändert
  sich nichts), danach die Werkzeuge dieses Repos (nur Datenaufbereitung, kein PiFlux-Code): `bahnhof.py` ergänzt
  `merkmale.sqlite` um Ebenen, Rolltreppen und Zugänge (Fassung 2), `gebaeudeteile.py` die Gebäudeteile in
  `gebaeude.mbtiles` um Art, Etagen und layer (Fassung 4). Dann prüft `pruefen.py` jede Datei, `probe_bericht.py`
  schreibt Abdeckung, Größen und die Gegenprobe der Kacheln nach `berichte/<land>.md`, `packen.py` packt nach
  `pakete/`. Länder und Zweig kommen aus `auftrag.txt`, wenn nichts angegeben ist.
- `werkzeuge/release.sh` lädt `pakete/` als neues Release hoch – mit dem angemeldeten `gh`, ohne Token im Repo: prüft
  jede Datei gegen ihr Manifest, legt eine Vorabfassung an, nimmt Fehlendes aus dem bisherigen Release mit, schreibt
  `pakete.json` und gibt erst nach Rückfrage frei (`--ja` ohne Rückfragen, `--trocken` zeigt nur, `--tag` setzt ein
  abgebrochenes Hochladen fort).

**Einmal einrichten** (Homebrew):

```bash
brew install python git gh osmium-tool node
```

```bash
python3 -m venv ~/.venv/cyberdeck-daten && ~/.venv/cyberdeck-daten/bin/pip install osmium numpy
```

```bash
gh auth login
```

`node` (≥ 22) braucht nur die Weltkarte, `osmium-tool` nur der Rückfall auf openstreetmap.fr.

**Ablauf** (App-Repo als Pfad, Python aus der venv):

```bash
export CYBERDECK_APP=~/Entwicklung/Cyberdeck PYTHON=~/.venv/cyberdeck-daten/bin/python3
```

```bash
werkzeuge/daten-lauf.sh --nur-pruefen
```

```bash
werkzeuge/daten-lauf.sh --land berlin
```

```bash
werkzeuge/release.sh
```

Weitere Schalter: `--land alle|keine|<land,land>`, `--zweig <zweig>`, `--ausgabe <ordner>`, `--welt` (Weltkarte),
`--fahrplan` (VBB), `--lod2` (3D-Dächer Berlin/Brandenburg), `--behalten` (Arbeitsordner nicht löschen), `--trocken`.
Ein Release mit nur einem neu gebauten Land ist vollständig – die übrigen Länder kommen aus dem bisherigen Release.

**Dauer und Platz** (Schätzung; das Protokoll `protokoll.txt` nennt die Zeit jedes Schritts):
Berlin etwa 15–30 Minuten, alle Länder einige Stunden (Bayern, NRW und Niedersachsen am längsten), die 3D-Dächer noch
einmal Stunden (Brandenburg: rund 19 000 ZIPs). Platz: alle Pakete gepackt rund 7,5 GB, dazu während des größten Landes
(NRW) rund 10 GB Arbeitsplatz – das Skript verlangt für mehr als drei Länder 25 GB frei (sonst 3 GB). Speicher: 16 GB
empfohlen (die Erzeuger halten die Knoten eines Landes im Speicher). Rohdaten und Arbeitsordner löscht es nach jedem
Land (außer mit `--behalten`).

**Prüfen ohne Netz:** `python3 -m unittest discover -s tests` (oder `python3 -m pytest tests`) – die Werkzeuge mit
erfundenen Beispielen und ein Durchlauf von `daten-lauf.sh`/`release.sh --trocken` mit Platzhalter-Erzeugern.

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
