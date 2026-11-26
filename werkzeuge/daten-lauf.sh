#!/usr/bin/env bash
# Daten-Lauf auf dem Mac (ersetzt die früheren GitHub-Workflows Daten, Welt, Fahrplan und LoD2): baut je Bundesland
# die Details für die App (Suche, Tippfehler, Straßennetz, Merkmale, Grenzen, 3D-Gebäude, Objektakte) mit den Erzeugern
# des App-Repos Cyberdeck, ergänzt sie mit den Werkzeugen dieses Repos (bahnhof.py, gebaeudeteile.py), prüft sie, schreibt
# einen Abdeckungsbericht und packt alles release-fertig (gzip je Datei, Manifest je Paket) in einen Ausgabeordner.
# Hochladen macht erst werkzeuge/release.sh (mit Rückfrage).
#
#   werkzeuge/daten-lauf.sh [--land berlin|alle|keine|<land,land>] [--app <pfad>] [--zweig <zweig>] [--ausgabe <ordner>]
#                           [--welt] [--fahrplan] [--lod2] [--behalten] [--nur-pruefen] [--trocken]
#
#   --land        Länder (Kennungen wie bei der Geofabrik, mit Komma), „alle“ oder „keine“ (nur Zusatzpakete);
#                 ohne Angabe die erste Zeile von auftrag.txt
#   --app         App-Repo Cyberdeck (sonst $CYBERDECK_APP). Dort wird nichts geändert: die Erzeuger laufen aus einer
#                 Kopie des Zweigs (git archive) in einem eigenen Arbeitsordner.
#   --zweig       Zweig/Commit der Erzeuger (sonst „zweig=“ aus auftrag.txt, sonst ios)
#   --ausgabe     Ausgabeordner (sonst $CYBERDECK_AUSGABE, sonst ~/Cyberdeck-Daten-Lauf)
#   --welt        zusätzlich die Weltkarte (welt, weltosm; braucht Node ≥ 22)
#   --fahrplan    zusätzlich den Fahrplan VBB (oepnv)
#   --lod2        zusätzlich die 3D-Dächer Berlin und Brandenburg (lod2-berlin, lod2-brandenburg; dauert Stunden)
#   --behalten    Arbeitsordner und Rohdaten nach dem Lauf nicht löschen
#   --nur-pruefen nur Voraussetzungen, App-Repo, Netz und Tests prüfen – nichts laden, nichts bauen
#   --trocken     nur zeigen, was laufen würde
#
# Ausgabe: <ausgabe>/pakete/ (<paket>--<pfad>.gz, <paket>.json – das lädt release.sh hoch), <ausgabe>/berichte/<land>.md
# (Abdeckung, Größen, Gegenprobe), <ausgabe>/lauf.json (Zweig, Commit, Datum), <ausgabe>/protokoll.txt.
# Quelle der Rohdaten: Geofabrik; ist ein Länderauszug dort nicht zu laden, der Deutschland-Auszug von openstreetmap.fr,
# an der Landesgrenze geschnitten (braucht osmium-tool). Die Shortbread-Grundkarte (für den Suchindex) gibt es nur bei
# der Geofabrik. Lizenz der Daten: © OpenStreetMap-Mitwirkende, ODbL (siehe README).

# Läuft mit der bash von macOS (3.2): keine assoziativen Felder, kein mapfile. Wortaufteilung von Länderlisten ist gewollt.
# shellcheck disable=SC2086,SC2116,SC1111
set -euo pipefail

REPO_DATEN=$(cd "$(dirname "$0")/.." && pwd)
WERKZEUGE="$REPO_DATEN/werkzeuge"
ALLE="baden-wuerttemberg bayern berlin brandenburg bremen hamburg hessen mecklenburg-vorpommern niedersachsen
nordrhein-westfalen rheinland-pfalz saarland sachsen sachsen-anhalt schleswig-holstein thueringen"
# Quellen (über die Umgebung umstellbar – für einen Spiegel oder die Tests mit file://)
GEOFABRIK=${CYBERDECK_GEOFABRIK:-https://download.geofabrik.de/europe/germany}
OSMFR=${CYBERDECK_OSMFR:-https://download.openstreetmap.fr/extracts/europe/germany-latest.osm.pbf}
VG250=${CYBERDECK_VG250:-https://daten.gdz.bkg.bund.de/produkte/vg/vg250_ebenen_0101/aktuell/vg250_01-01.utm32s.gpkg.ebenen.zip}
PY=${PYTHON:-python3}

LAND_WAHL=""; APP=${CYBERDECK_APP:-}; ZWEIG=""; AUSGABE=${CYBERDECK_AUSGABE:-$HOME/Cyberdeck-Daten-Lauf}
WELT=0; FAHRPLAN=0; LOD2=0; BEHALTEN=0; NUR_PRUEFEN=0; TROCKEN=0

hilfe() { sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --land) LAND_WAHL=${2:?}; shift ;;
    --app) APP=${2:?}; shift ;;
    --zweig) ZWEIG=${2:?}; shift ;;
    --ausgabe) AUSGABE=${2:?}; shift ;;
    --welt) WELT=1 ;;
    --fahrplan) FAHRPLAN=1 ;;
    --lod2) LOD2=1 ;;
    --behalten) BEHALTEN=1 ;;
    --nur-pruefen) NUR_PRUEFEN=1 ;;
    --trocken) TROCKEN=1 ;;
    -h|--hilfe|--help) hilfe 0 ;;
    *) echo "Unbekannte Option: $1" >&2; hilfe 2 ;;
  esac
  shift
done

# ---------- Ausgabe und Hilfen ----------

PROTOKOLL=/dev/null
sag() { printf '%s\n' "$*" | tee -a "$PROTOKOLL"; }
fehler() { printf 'FEHLER: %s\n' "$*" | tee -a "$PROTOKOLL" >&2; exit 1; }
warnung() { printf 'Achtung: %s\n' "$*" | tee -a "$PROTOKOLL" >&2; }

# Befehl ausführen (bei --trocken nur zeigen); Ausgabe ins Protokoll. %q unter LC_ALL=C: die bash 3.2 von macOS
# zerlegt unter UTF-8 Zeichen wie „–“ in halb maskierte Bytes (ungültiges UTF-8 im Protokoll).
lauf() {
  printf '→' | tee -a "$PROTOKOLL"; ( export LC_ALL=C; printf ' %q' "$@" ) | tee -a "$PROTOKOLL"; printf '\n' | tee -a "$PROTOKOLL"
  [ "$TROCKEN" = 1 ] && return 0
  "$@" 2>&1 | tee -a "$PROTOKOLL"
  return "${PIPESTATUS[0]}"
}

# Schritt mit Dauer
schritt() {
  local name=$1; shift
  local anfang=$SECONDS
  sag "== $name"
  lauf "$@" || fehler "$name gescheitert"
  [ "$TROCKEN" = 1 ] || sag "   ($name: $((SECONDS - anfang)) s)"
}

holen() {  # holen <url> <ziel>
  lauf curl -fL --retry 5 --retry-delay 20 -sS -o "$2.teil" "$1" && { [ "$TROCKEN" = 1 ] || mv "$2.teil" "$2"; }
}

frei_gb() { df -Pk "$1" | awk 'NR == 2 { printf "%d", $4 / 1048576 }'; }

# ---------- Auswahl ----------

auftrag_wert() {  # erste Zeile ohne # (Länder) bzw. zweig=
  grep -v '^#' "$REPO_DATEN/auftrag.txt" 2>/dev/null | tr -d ' \r' | { if [ "$1" = zweig ]; then grep '^zweig=' | cut -d= -f2; else grep -v '^zweig=' | grep -v '^$'; fi; } | head -1 || true
}
[ -n "$LAND_WAHL" ] || LAND_WAHL=$(auftrag_wert laender)
[ -n "$LAND_WAHL" ] || LAND_WAHL=berlin
[ -n "$ZWEIG" ] || ZWEIG=$(auftrag_wert zweig)
[ -n "$ZWEIG" ] || ZWEIG=ios
case "$LAND_WAHL" in
  alle) LAENDER=$(echo $ALLE) ;;
  keine) LAENDER="" ;;
  *) LAENDER=$(echo "$LAND_WAHL" | tr ',' ' ') ;;
esac
for land in $LAENDER; do
  case " $(echo $ALLE) " in *" $land "*) ;; *) fehler "Unbekanntes Land: $land (Kennungen: $(echo $ALLE))" ;; esac
done
[ -n "$LAENDER" ] || [ "$WELT$FAHRPLAN$LOD2" != 000 ] || fehler "Nichts zu tun: --land keine ohne --welt/--fahrplan/--lod2"

# ---------- Voraussetzungen ----------

pruefen() {
  local fehlt=""
  command -v curl > /dev/null || fehlt="$fehlt curl"
  command -v git > /dev/null || fehlt="$fehlt git"
  command -v "$PY" > /dev/null || fehlt="$fehlt python3"
  [ -z "$fehlt" ] || fehler "Es fehlt:$fehlt – auf dem Mac: brew install$fehlt"
  "$PY" -c 'import sys; assert sys.version_info >= (3, 10)' 2> /dev/null || fehler "$PY ist älter als 3.10 – brew install python"
  if ! "$PY" -c 'import osmium, numpy' 2> /dev/null; then
    fehler "$PY findet osmium (pyosmium) oder numpy nicht. Einmal einrichten:
    python3 -m venv ~/.venv/cyberdeck-daten && ~/.venv/cyberdeck-daten/bin/pip install osmium numpy
  und dann mit PYTHON=~/.venv/cyberdeck-daten/bin/python3 $0 … starten"
  fi
  if ! command -v osmium > /dev/null; then
    warnung "osmium-tool fehlt (brew install osmium-tool) – nur nötig, wenn die Geofabrik nicht erreichbar ist"
  fi
  if [ "$WELT" = 1 ]; then
    command -v node > /dev/null || fehler "--welt braucht Node ≥ 22 – brew install node"
    [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ] || fehler "--welt braucht Node ≥ 22 (node:sqlite)"
  fi
  [ -n "$APP" ] || fehler "Pfad zum App-Repo fehlt: --app <pfad> oder CYBERDECK_APP=<pfad>"
  [ -d "$APP/.git" ] || [ -f "$APP/.git" ] || fehler "$APP ist kein Git-Repo"
  APP_COMMIT=$(git -C "$APP" rev-parse --verify --quiet "$ZWEIG^{commit}" || git -C "$APP" rev-parse --verify --quiet "origin/$ZWEIG^{commit}" || true)
  [ -n "$APP_COMMIT" ] || fehler "Zweig $ZWEIG gibt es in $APP nicht (auch nicht als origin/$ZWEIG) – vorher git fetch im App-Repo"
  git -C "$APP" cat-file -e "$APP_COMMIT:tools/erzeugen/merkmale-erzeugen.py" 2> /dev/null \
    || fehler "$ZWEIG in $APP hat keine Erzeuger (tools/erzeugen/)"
  sag "App-Repo: $APP, Zweig $ZWEIG = ${APP_COMMIT:0:12} ($(git -C "$APP" log -1 --format=%cs "$APP_COMMIT"))"
  sag "Python: $("$PY" -c 'import sys, osmium.version as o; print(sys.version.split()[0], "pyosmium", o.pyosmium_release)')"
}

tests() {
  sag "== Tests der Werkzeuge"
  lauf "$PY" -m unittest discover -s "$REPO_DATEN/tests" || fehler "Tests gescheitert"
}

# ---------- Erzeuger aus dem App-Repo (Kopie) ----------

hat_erzeuger() {  # hat_erzeuger <datei in tools/erzeugen>: im gewählten Commit vorhanden?
  git -C "$APP" cat-file -e "$APP_COMMIT:tools/erzeugen/$1" 2> /dev/null
}

wechsel() {  # in den Arbeitsordner (trocken: gibt es ihn nicht)
  if [ "$TROCKEN" = 1 ]; then sag "→ cd $1"; else cd "$1" || exit 1; fi
}

erzeuger_kopie() {  # erzeuger_kopie <ordner>: tools/ und piflux/ des Zweigs, ohne das App-Repo anzufassen
  lauf rm -rf "$1"
  lauf mkdir -p "$1/kartendaten/osm" "$1/kartendaten/laender"
  if [ "$TROCKEN" = 1 ]; then
    sag "→ git -C $APP archive $APP_COMMIT tools piflux | tar -x -C $1"
  else
    git -C "$APP" archive "$APP_COMMIT" tools piflux | tar -x -C "$1"
  fi
}

# ---------- Rohdaten ----------

iso() {  # ISO-3166-2-Kürzel des Landes (für den Schnitt aus dem Deutschland-Auszug)
  case "$1" in
    baden-wuerttemberg) echo DE-BW ;; bayern) echo DE-BY ;; berlin) echo DE-BE ;; brandenburg) echo DE-BB ;;
    bremen) echo DE-HB ;; hamburg) echo DE-HH ;; hessen) echo DE-HE ;; mecklenburg-vorpommern) echo DE-MV ;;
    niedersachsen) echo DE-NI ;; nordrhein-westfalen) echo DE-NW ;; rheinland-pfalz) echo DE-RP ;;
    saarland) echo DE-SL ;; sachsen) echo DE-SN ;; sachsen-anhalt) echo DE-ST ;; schleswig-holstein) echo DE-SH ;;
    thueringen) echo DE-TH ;;
  esac
}

md5_pruefen() {  # md5_pruefen <datei> <md5-datei> (wie md5sum -c, ohne GNU-Werkzeuge)
  [ "$TROCKEN" = 1 ] && return 0
  "$PY" - "$1" "$2" <<'EOF'
import hashlib, sys
soll = open(sys.argv[2]).read().split()[0]
h = hashlib.md5()
with open(sys.argv[1], "rb") as f:
    for block in iter(lambda: f.read(1 << 23), b""):
        h.update(block)
sys.exit(0 if h.hexdigest() == soll else f"md5 passt nicht: {sys.argv[1]}")
EOF
}

rohdaten() {  # rohdaten <land> <ziel.osm.pbf>
  local land=$1 ziel=$2
  if holen "$GEOFABRIK/$land-latest.osm.pbf" "$ziel" && holen "$GEOFABRIK/$land-latest.osm.pbf.md5" "$ziel.md5" \
      && md5_pruefen "$ziel" "$ziel.md5"; then
    rm -f "$ziel.md5"
    return 0
  fi
  warnung "$land: Geofabrik nicht erreichbar – Deutschland-Auszug von openstreetmap.fr, an der Landesgrenze geschnitten"
  command -v osmium > /dev/null || fehler "Für den Rückfall fehlt osmium-tool: brew install osmium-tool"
  local quellen="$AUSGABE/quellen"
  lauf mkdir -p "$quellen"
  if [ ! -s "$quellen/germany-latest.osm.pbf" ]; then
    holen "$OSMFR" "$quellen/germany-latest.osm.pbf" || fehler "Auch openstreetmap.fr nicht erreichbar"
  fi
  if [ ! -s "$quellen/grenzen-de.osm.pbf" ]; then
    lauf osmium tags-filter "$quellen/germany-latest.osm.pbf" r/boundary=administrative -o "$quellen/grenzen-de.osm.pbf" \
      --overwrite || fehler "Grenzen aus dem Deutschland-Auszug"
  fi
  local relation
  if [ "$TROCKEN" = 1 ]; then relation=0; else
    relation=$("$PY" - "$quellen/grenzen-de.osm.pbf" "$(iso "$land")" <<'EOF'
import sys, osmium
for r in osmium.FileProcessor(sys.argv[1], osmium.osm.RELATION):
    if r.tags.get("ISO3166-2") == sys.argv[2] and r.tags.get("admin_level") == "4":
        print(r.id)
        break
EOF
)
  fi
  [ -n "$relation" ] || fehler "$land: Landesgrenze ($(iso "$land")) im Deutschland-Auszug nicht gefunden"
  lauf osmium getid -r "$quellen/grenzen-de.osm.pbf" "r$relation" -o "$quellen/grenze-$land.osm" --overwrite
  lauf osmium extract -p "$quellen/grenze-$land.osm" -s smart "$quellen/germany-latest.osm.pbf" -o "$ziel" --overwrite \
    || fehler "$land: Schnitt aus dem Deutschland-Auszug"
}

# ---------- ein Land ----------

land_bauen() {
  local land=$1 anfang=$SECONDS
  local arbeit="$AUSGABE/arbeit/$land"
  local app="$arbeit/app" k="$arbeit/app/kartendaten"
  sag ""
  sag "######## $land ($(date '+%H:%M'))"
  erzeuger_kopie "$app"
  lauf mkdir -p "$arbeit/vorher" "$arbeit/ergebnis"

  sag "== Rohdaten und Grundkarte"
  rohdaten "$land" "$k/osm/$land-latest.osm.pbf"
  # Namen für den Suchindex kommen aus den Kacheln; Berlin steckt in der Grundkarte Brandenburg (laender.py)
  local karte=$land; [ "$land" = berlin ] && karte=brandenburg
  local karte_datei="$AUSGABE/quellen/$karte-shortbread-1.0.mbtiles"
  lauf mkdir -p "$AUSGABE/quellen"
  if [ ! -s "$karte_datei" ]; then
    holen "$GEOFABRIK/$karte-shortbread-1.0.mbtiles" "$karte_datei" \
      || fehler "Shortbread-Grundkarte $karte nur bei der Geofabrik – ohne sie kein Suchindex"
  fi
  lauf ln -sf "$karte_datei" "$k/laender/$karte-shortbread-1.0.mbtiles"

  ( wechsel "$app"
    schritt "Suchindex" "$PY" tools/erzeugen/suchindex-erzeugen.py
    schritt "Tippfehler-Wörter" "$PY" tools/erzeugen/suchwoerter-erzeugen.py
    schritt "Straßennetz" "$PY" tools/erzeugen/strassennetz-erzeugen.py
    schritt "Merkmale" "$PY" tools/erzeugen/merkmale-erzeugen.py
    lauf cp kartendaten/merkmale.sqlite "$arbeit/vorher/" || exit 1
    schritt "Merkmale für Bahnhöfe (bahnhof.py)" "$PY" "$WERKZEUGE/bahnhof.py" kartendaten/merkmale.sqlite \
      "kartendaten/osm/$land-latest.osm.pbf"
    if hat_erzeuger grenzen-erzeugen.py && git -C "$APP" show "$APP_COMMIT:tools/erzeugen/grenzen-erzeugen.py" | grep -q -- "--land"; then
      lauf mkdir -p kartendaten/vg250 || exit 1
      if [ ! -s "$AUSGABE/quellen/vg250.zip" ]; then
        holen "$VG250" "$AUSGABE/quellen/vg250.zip" || warnung "VG250 nicht geladen – Kreise und Gemeinden aus OSM"
      fi
      if [ -s "$AUSGABE/quellen/vg250.zip" ]; then lauf ln -sf "$AUSGABE/quellen/vg250.zip" kartendaten/vg250/vg250.zip; fi
      schritt "Verwaltungsgrenzen" "$PY" tools/erzeugen/grenzen-erzeugen.py --land "$land" --ziel kartendaten/grenzen.sqlite
      lauf rm -rf kartendaten/vg250
    else
      warnung "grenzen-erzeugen.py ohne --land in $ZWEIG – Paket ohne grenzen.sqlite"
    fi
    schritt "3D-Gebäude" "$PY" tools/erzeugen/gebaeude-erzeugen.py --ohne-lod2
    lauf cp kartendaten/gebaeude.mbtiles "$arbeit/vorher/" || exit 1
    schritt "Gebäudeteile genauer (gebaeudeteile.py)" "$PY" "$WERKZEUGE/gebaeudeteile.py" kartendaten/gebaeude.mbtiles \
      "kartendaten/osm/$land-latest.osm.pbf"
    for e in geschosse eingaenge objekt; do
      if hat_erzeuger "$e-erzeugen.py"; then
        schritt "Objektakte: $e" "$PY" "tools/erzeugen/$e-erzeugen.py"
      else
        warnung "$e-erzeugen.py fehlt in $ZWEIG"
      fi
    done
  ) || fehler "$land: Erzeuger gescheitert"

  sag "== Prüfen und Bericht"
  local teil
  for teil in suchindex.sqlite suchwoerter.sqlite merkmale.sqlite gebaeude.mbtiles strassennetz; do
    [ "$TROCKEN" = 1 ] || [ -e "$k/$teil" ] || fehler "$land: $teil fehlt"
    lauf mv "$k/$teil" "$arbeit/ergebnis/"
  done
  for teil in grenzen.sqlite geschosse.sqlite eingaenge.sqlite objekt.sqlite; do
    if [ "$TROCKEN" = 1 ] || [ -f "$k/$teil" ]; then lauf mv "$k/$teil" "$arbeit/ergebnis/"; fi
  done
  lauf "$PY" "$WERKZEUGE/pruefen.py" "$arbeit/ergebnis" || fehler "$land: Prüfung der Dateien"
  lauf mkdir -p "$AUSGABE/berichte"
  if [ "$TROCKEN" = 1 ]; then
    sag "→ $PY $WERKZEUGE/probe_bericht.py $arbeit/vorher $arbeit/ergebnis > $AUSGABE/berichte/$land.md"
  else
    { echo "# $land – $(date '+%Y-%m-%d %H:%M'), Erzeuger $ZWEIG ${APP_COMMIT:0:12}"; echo;
      "$PY" "$WERKZEUGE/probe_bericht.py" "$arbeit/vorher" "$arbeit/ergebnis"; } > "$AUSGABE/berichte/$land.md" \
      || { cat "$AUSGABE/berichte/$land.md"; fehler "$land: Gegenprobe der Gebäudekacheln"; }
    grep -E "^\| .(highway=elevator|railway=platform)|^Rolltreppen \(nachher|^Gebäudeteile in Zoom" "$AUSGABE/berichte/$land.md" \
      | tee -a "$PROTOKOLL" || true
  fi
  paket_packen "$land" "$arbeit/ergebnis"
  [ "$BEHALTEN" = 1 ] || lauf rm -rf "$arbeit" "$k/osm/$land-latest.osm.pbf"
  # die Grundkarte Brandenburg braucht auch Berlin – erst löschen, wenn keins der beiden mehr kommt
  local karte_noch=0
  if [ "$karte" = brandenburg ]; then case "$NOCH" in *" berlin "*|*" brandenburg "*) karte_noch=1 ;; esac; fi
  [ "$BEHALTEN" = 1 ] || [ "$karte_noch" = 1 ] || lauf rm -f "$karte_datei"
  sag "######## $land fertig in $(( (SECONDS - anfang) / 60 )) min"
}

paket_packen() {  # paket_packen <paket> <ordner> [zusatz-json]: alte Dateien des Pakets in pakete/ zuerst weg
  lauf mkdir -p "$AUSGABE/pakete"
  [ "$TROCKEN" = 1 ] || find "$AUSGABE/pakete" -maxdepth 1 \( -name "$1--*" -o -name "$1.json" \) -delete
  if [ $# -ge 3 ]; then
    lauf "$PY" "$WERKZEUGE/packen.py" "$1" "$2" "$AUSGABE/pakete" "$3" || fehler "$1: packen"
  else
    lauf "$PY" "$WERKZEUGE/packen.py" "$1" "$2" "$AUSGABE/pakete" || fehler "$1: packen"
  fi
}

# ---------- Zusatzpakete ----------

welt_bauen() {
  local arbeit="$AUSGABE/arbeit/welt"
  sag ""; sag "######## Weltkarte"
  erzeuger_kopie "$arbeit/app"
  ( wechsel "$arbeit/app"
    schritt "Welt-Übersicht (Natural Earth, Zoom 0–7)" "$PY" tools/erzeugen/welt-erzeugen.py
    schritt "Welt-Grundkarte (OpenStreetMap über VersaTiles, Zoom 0–8)" node tools/erzeugen/welt-osm.mjs 8
  ) || fehler "Weltkarte gescheitert"
  lauf mkdir -p "$arbeit/welt" "$arbeit/weltosm"
  lauf mv "$arbeit/app/kartendaten/welt.mbtiles" "$arbeit/welt/"
  lauf mv "$arbeit/app/kartendaten/welt-osm.mbtiles" "$arbeit/weltosm/"
  paket_packen welt "$arbeit/welt"
  paket_packen weltosm "$arbeit/weltosm"
  [ "$BEHALTEN" = 1 ] || lauf rm -rf "$arbeit"
}

fahrplan_bauen() {
  local arbeit="$AUSGABE/arbeit/oepnv"
  sag ""; sag "######## Fahrplan VBB"
  erzeuger_kopie "$arbeit/app"
  ( wechsel "$arbeit/app" && schritt "VBB-Fahrplan laden und umwandeln" "$PY" tools/erzeugen/oepnv-erzeugen.py --neu ) \
    || fehler "Fahrplan gescheitert"
  lauf mkdir -p "$arbeit/oepnv"
  lauf mv "$arbeit/app/kartendaten/oepnv.sqlite" "$arbeit/oepnv/"
  paket_packen oepnv "$arbeit/oepnv"
  [ "$BEHALTEN" = 1 ] || lauf rm -rf "$arbeit"
}

lod2_bauen() {
  local land arbeit lizenz zusatz
  for land in berlin brandenburg; do
    arbeit="$AUSGABE/arbeit/lod2-$land"
    sag ""; sag "######## 3D-Dächer $land"
    erzeuger_kopie "$arbeit/app"
    lauf mkdir -p "$arbeit/ergebnis"
    ( wechsel "$arbeit/app"
      schritt "Dächer lesen ($land)" "$PY" tools/erzeugen/lod2-dach-erzeugen.py teil --land "$land" --teile 1 --teil 0 \
        --ziel "$arbeit/teil.sqlite"
      schritt "Zusammenfügen ($land)" "$PY" tools/erzeugen/lod2-dach-erzeugen.py zusammen --land "$land" \
        --ziel "$arbeit/ergebnis/lod2.sqlite" "$arbeit/teil.sqlite"
    ) || fehler "3D-Dächer $land gescheitert"
    if [ "$TROCKEN" = 1 ]; then zusatz='{"art": "lod2", "fuer": "'$land'", "optional": true, "lizenz": "…"}'; else
      lizenz=$("$PY" -c "import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute(\"SELECT wert FROM info WHERE schluessel='lizenz'\").fetchone()[0])" "$arbeit/ergebnis/lod2.sqlite")
      zusatz=$(LAND="$land" LIZ="$lizenz" "$PY" -c 'import json, os; print(json.dumps({"art": "lod2", "fuer": os.environ["LAND"], "optional": True, "lizenz": os.environ["LIZ"]}, ensure_ascii=False))')
    fi
    paket_packen "lod2-$land" "$arbeit/ergebnis" "$zusatz"
    [ "$BEHALTEN" = 1 ] || lauf rm -rf "$arbeit"
  done
}

# ---------- Ablauf ----------

if [ "$TROCKEN" = 0 ] && [ "$NUR_PRUEFEN" = 0 ]; then
  mkdir -p "$AUSGABE"
  PROTOKOLL="$AUSGABE/protokoll.txt"
  sag "==================== Daten-Lauf $(date '+%Y-%m-%d %H:%M')"
fi
sag "Länder: ${LAENDER:-keine}; Zusatz:$([ "$WELT" = 1 ] && echo " welt")$([ "$FAHRPLAN" = 1 ] && echo " fahrplan")$([ "$LOD2" = 1 ] && echo " lod2"); Ausgabe: $AUSGABE"
pruefen
[ "${CYBERDECK_OHNE_TESTS:-0}" = 1 ] || tests
if [ "$NUR_PRUEFEN" = 1 ]; then
  for url in "$GEOFABRIK/berlin-latest.osm.pbf.md5" "$OSMFR"; do
    if curl -fsSI --max-time 20 "$url" > /dev/null; then sag "Netz: $url erreichbar"; else warnung "Netz: $url nicht erreichbar"; fi
  done
  if [ -d "$(dirname "$AUSGABE")" ]; then sag "Frei unter $(dirname "$AUSGABE"): $(frei_gb "$(dirname "$AUSGABE")") GB"; fi
  sag "Prüfung fertig – nichts geladen, nichts gebaut."
  exit 0
fi

if [ "$TROCKEN" = 0 ]; then
  noetig=3; [ "$(echo $LAENDER | wc -w)" -gt 3 ] && noetig=25
  [ "$(frei_gb "$AUSGABE")" -ge "$noetig" ] || fehler "Zu wenig Platz unter $AUSGABE: $(frei_gb "$AUSGABE") GB frei, nötig etwa $noetig GB"
fi

BEGINN=$SECONDS
NOCH=" $LAENDER "
for land in $LAENDER; do
  NOCH=${NOCH/ $land / }
  land_bauen "$land"
done
[ "$WELT" = 0 ] || welt_bauen
[ "$FAHRPLAN" = 0 ] || fahrplan_bauen
[ "$LOD2" = 0 ] || lod2_bauen

if [ "$TROCKEN" = 0 ]; then
  LAND_LISTE="$LAENDER" ZWEIG="$ZWEIG" COMMIT="$APP_COMMIT" "$PY" - "$AUSGABE/lauf.json" <<'EOF'
import json, os, sys, time
pfad = sys.argv[1]
alt = json.load(open(pfad)) if os.path.exists(pfad) else {}
alt.setdefault("laeufe", []).append({"zeit": time.strftime("%Y-%m-%dT%H:%M:%S"), "laender": os.environ["LAND_LISTE"].split(),
                                     "zweig": os.environ["ZWEIG"], "commit": os.environ["COMMIT"]})
alt.update({"zweig": os.environ["ZWEIG"], "commit": os.environ["COMMIT"]})
json.dump(alt, open(pfad, "w"), ensure_ascii=False, indent=1)
EOF
  [ "$BEHALTEN" = 1 ] || rm -rf "$AUSGABE/arbeit" "$AUSGABE/quellen"
  sag ""
  sag "Fertig in $(( (SECONDS - BEGINN) / 60 )) min. Pakete in $AUSGABE/pakete, Berichte in $AUSGABE/berichte."
  sag "Hochladen (mit Rückfrage): $REPO_DATEN/werkzeuge/release.sh --ausgabe $AUSGABE"
fi
