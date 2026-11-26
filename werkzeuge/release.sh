#!/usr/bin/env bash
# Lädt die fertigen Pakete eines Daten-Laufs (werkzeuge/daten-lauf.sh) als neues GitHub-Release hoch – vom Mac, mit dem
# angemeldeten gh (kein Token im Repo). Ablauf wie früher in den Workflows:
#   1. prüfen: gh angemeldet, jede Datei der Manifeste da, Größe und sha256 wie im Manifest
#   2. Release daten-JJJJ-MM-TT-N als Vorabfassung anlegen, Dateien hochladen (Manifeste zuletzt)
#   3. was der Lauf nicht gebaut hat (andere Länder, Welt, Fahrplan, 3D-Dächer), aus dem bisherigen Release mitnehmen
#      (werkzeuge/mitnehmen.py – mit Prüfsummen), damit das neue Release vollständig ist
#   4. pakete.json aus allen Manifesten des Releases (werkzeuge/verzeichnis.py) – das Verzeichnis, das die App liest
#   5. erst wenn alle 16 Länder, welt, weltosm und oepnv darin stehen: freigeben („latest“; die App sieht es dann)
# Vor dem Anlegen und vor dem Freigeben fragt es nach (außer mit --ja).
#
#   werkzeuge/release.sh [--ausgabe <ordner>] [--repo <besitzer/name>] [--tag <tag>] [--ja] [--trocken] [--ohne-freigabe]
#                        [--trotzdem]
#
#   --tag            in diese (schon angelegte) Vorabfassung hochladen, z. B. nach einem Abbruch – sonst neu
#                    daten-JJJJ-MM-TT-N (N: nächste freie Nummer des Tages)
#   --ausgabe        Ausgabeordner des Daten-Laufs (sonst $CYBERDECK_AUSGABE, sonst ~/Cyberdeck-Daten-Lauf)
#   --repo           Ziel (sonst feinschmeckerr/Cyberdeck-Daten)
#   --ja             ohne Rückfragen
#   --trocken        nur prüfen und zeigen, was geschähe – nichts anlegen, nichts hochladen
#   --ohne-freigabe  als Vorabfassung lassen (die App sieht es nicht)
#   --trotzdem       auch freigeben, wenn im Verzeichnis Pakete fehlen

# Läuft mit der bash von macOS (3.2). Wortaufteilung von Paketlisten ist gewollt.
# shellcheck disable=SC2086,SC1111
set -euo pipefail

REPO_DATEN=$(cd "$(dirname "$0")/.." && pwd)
WERKZEUGE="$REPO_DATEN/werkzeuge"
AUSGABE=${CYBERDECK_AUSGABE:-$HOME/Cyberdeck-Daten-Lauf}
ZIEL=feinschmeckerr/Cyberdeck-Daten
JA=0; TROCKEN=0; FREIGABE=1; TROTZDEM=0; TAG=""
PY=${PYTHON:-python3}
ALLE="baden-wuerttemberg bayern berlin brandenburg bremen hamburg hessen mecklenburg-vorpommern niedersachsen
nordrhein-westfalen rheinland-pfalz saarland sachsen sachsen-anhalt schleswig-holstein thueringen"
ZUSATZ="welt weltosm oepnv lod2-berlin lod2-brandenburg"
PFLICHT_ZUSATZ="welt weltosm oepnv"
NOTIZ="Details der Bundesländer für die PiFlux-App, erzeugt auf dem Mac (werkzeuge/daten-lauf.sh). © OpenStreetMap-Mitwirkende, ODbL 1.0 – über Geofabrik. Verwaltungsgrenzen (Kreise, Gemeinden): © GeoBasis-DE / BKG, dl-de/by-2-0. Fahrplan: VBB, CC BY 4.0. 3D-Dächer: Berlin dl-de/zero-2.0, Brandenburg © GeoBasis-DE/LGB, dl-de/by-2.0."

hilfe() { sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --ausgabe) AUSGABE=${2:?}; shift ;;
    --repo) ZIEL=${2:?}; shift ;;
    --tag) TAG=${2:?}; shift ;;
    --ja) JA=1 ;;
    --trocken) TROCKEN=1 ;;
    --ohne-freigabe) FREIGABE=0 ;;
    --trotzdem) TROTZDEM=1 ;;
    -h|--hilfe|--help) hilfe 0 ;;
    *) echo "Unbekannte Option: $1" >&2; hilfe 2 ;;
  esac
  shift
done

fehler() { printf 'FEHLER: %s\n' "$*" >&2; exit 1; }
lauf() {
  printf '→'; ( export LC_ALL=C; printf ' %q' "$@" ); printf '\n'
  [ "$TROCKEN" = 1 ] || "$@"
}
frage() {  # frage <text>: weiter nur mit j
  [ "$JA" = 1 ] && return 0
  [ "$TROCKEN" = 1 ] && { echo "(Rückfrage: $1)"; return 0; }
  local antwort
  printf '%s [j/N] ' "$1"
  read -r antwort
  case "$antwort" in j|J|ja|Ja) return 0 ;; *) echo "Abgebrochen."; exit 1 ;; esac
}

PAKETE="$AUSGABE/pakete"
[ -d "$PAKETE" ] || fehler "Keine Pakete in $PAKETE – erst werkzeuge/daten-lauf.sh"
command -v gh > /dev/null || fehler "gh fehlt – brew install gh, dann gh auth login"
if [ "$TROCKEN" = 0 ]; then
  gh auth status > /dev/null 2>&1 || fehler "gh ist nicht angemeldet – gh auth login"
  gh repo view "$ZIEL" --json name > /dev/null 2>&1 || fehler "$ZIEL ist mit gh nicht erreichbar"
fi

# ---------- 1. prüfen ----------

echo "== Pakete in $PAKETE prüfen (Größe und sha256 je Datei)"
LOKAL=$("$PY" - "$PAKETE" <<'EOF'
import hashlib, json, sys
from pathlib import Path
ordner = Path(sys.argv[1])
fehler, pakete = [], []
for manifest in sorted(ordner.glob("*.json")):
    if manifest.name == "pakete.json":
        continue
    m = json.loads(manifest.read_text(encoding="utf-8"))
    if m.get("land") != manifest.stem:
        fehler.append(f"{manifest.name}: land {m.get('land')!r}")
    for d in m["dateien"]:
        teile = d.get("teile") or [{"name": d["name"], "groesse": d["gz_groesse"], "sha256": d["gz_sha256"]}]
        for t in teile:
            pfad = ordner / t["name"]
            if not pfad.is_file() or pfad.stat().st_size != t["groesse"]:
                fehler.append(f"{t['name']} fehlt oder hat die falsche Größe")
                continue
            h = hashlib.sha256()
            with open(pfad, "rb") as f:
                for block in iter(lambda: f.read(1 << 23), b""):
                    h.update(block)
            if h.hexdigest() != t["sha256"]:
                fehler.append(f"{t['name']}: sha256 passt nicht zum Manifest")
    pakete.append(f"{m['land']}:{m['gz_groesse']}")
for f in fehler:
    print("FEHLER", f, file=sys.stderr)
if fehler:
    sys.exit(1)
print(" ".join(pakete))
EOF
) || fehler "Pakete passen nicht zu ihren Manifesten – Daten-Lauf wiederholen"
[ -n "$LOKAL" ] || fehler "Keine Manifeste in $PAKETE"
NAMEN=""; SUMME=0
for eintrag in $LOKAL; do NAMEN="$NAMEN ${eintrag%%:*}"; SUMME=$((SUMME + ${eintrag##*:})); done
NAMEN=${NAMEN# }
echo "Gebaut: $NAMEN ($((SUMME / 1000000)) MB gepackt)"

MITNEHMEN=""
for paket in $ALLE $ZUSATZ; do
  case " $NAMEN " in *" $paket "*) ;; *) MITNEHMEN="$MITNEHMEN $paket" ;; esac
done
MITNEHMEN=${MITNEHMEN# }

# ---------- 2. anlegen und hochladen ----------

FORTSETZEN=0
if [ -n "$TAG" ]; then
  if [ "$TROCKEN" = 0 ] && gh release view "$TAG" -R "$ZIEL" > /dev/null 2>&1; then
    [ "$(gh release view "$TAG" -R "$ZIEL" --json isPrerelease -q .isPrerelease)" = true ] \
      || fehler "$TAG ist schon freigegeben – nicht weiter hineinladen"
    FORTSETZEN=1
  fi
else
  DATUM=$(date -u +%Y-%m-%d)
  N=1
  if [ "$TROCKEN" = 0 ]; then
    while gh release view "daten-$DATUM-$N" -R "$ZIEL" > /dev/null 2>&1; do N=$((N + 1)); done
  fi
  TAG="daten-$DATUM-$N"
fi
ERZEUGER=""
if [ -f "$AUSGABE/lauf.json" ]; then
  ERZEUGER=$("$PY" -c 'import json, sys; d = json.load(open(sys.argv[1])); print("Erzeuger: Cyberdeck", d.get("zweig"), str(d.get("commit"))[:12])' "$AUSGABE/lauf.json")
fi
echo
echo "Release:   $TAG in $ZIEL"
echo "Neu:       $NAMEN"
echo "Mitnehmen: ${MITNEHMEN:-–} (aus dem bisherigen Release)"
[ -z "$ERZEUGER" ] || echo "$ERZEUGER"
if [ "$FORTSETZEN" = 1 ]; then
  frage "In die bestehende Vorabfassung $TAG hochladen (vorhandene Dateien werden ersetzt)?"
else
  frage "Release $TAG anlegen und hochladen?"
  lauf gh release create "$TAG" -R "$ZIEL" --prerelease --title "Kartendaten $TAG" --notes "$NOTIZ ${ERZEUGER}"
fi
# Daten zuerst, Manifeste zuletzt: ein Manifest steht nur im Release, wenn seine Dateien schon da sind (wie mitnehmen.py)
find "$PAKETE" -maxdepth 1 -type f ! -name '*.json' -print0 | sort -z | while IFS= read -r -d '' datei; do
  lauf gh release upload "$TAG" -R "$ZIEL" --clobber "$datei" \
    || fehler "Hochladen von $datei gescheitert – fortsetzen mit: $0 --ausgabe $AUSGABE --tag $TAG"
done
for paket in $NAMEN; do
  lauf gh release upload "$TAG" -R "$ZIEL" --clobber "$PAKETE/$paket.json" || fehler "Hochladen von $paket.json gescheitert"
done

# ---------- 3. mitnehmen ----------

if [ -n "$MITNEHMEN" ]; then
  echo "== Aus dem bisherigen Release mitnehmen: $MITNEHMEN"
  GITHUB_REPOSITORY="$ZIEL" lauf "$PY" "$WERKZEUGE/mitnehmen.py" "$TAG" $MITNEHMEN \
    || fehler "Mitnehmen gescheitert – $TAG bleibt Vorabfassung (die App sieht es nicht)"
fi

# ---------- 4. Verzeichnis ----------

echo "== pakete.json"
MANIFESTE=$(mktemp -d)
trap 'rm -rf "$MANIFESTE"' EXIT
lauf gh release download "$TAG" -R "$ZIEL" -D "$MANIFESTE" --pattern '*.json'
lauf rm -f "$MANIFESTE/pakete.json"
if [ "$TROCKEN" = 1 ]; then
  echo "→ $PY $WERKZEUGE/verzeichnis.py $MANIFESTE $TAG > $MANIFESTE/pakete.json"
  FEHLT=""
else
  # erst daneben schreiben, dann verschieben: sonst läge eine leere pakete.json unter den Manifesten, die es liest
  "$PY" "$WERKZEUGE/verzeichnis.py" "$MANIFESTE" "$TAG" > "$MANIFESTE.pakete.json"
  mv "$MANIFESTE.pakete.json" "$MANIFESTE/pakete.json"
  FEHLT=$("$PY" - "$MANIFESTE/pakete.json" $ALLE $PFLICHT_ZUSATZ <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
da = {l["land"]: l["gz_groesse"] for l in d["laender"]}
for land, groesse in sorted(da.items()):
    print(f"  {land:24} {groesse / 1e6:8.0f} MB", file=sys.stderr)
print(" ".join(p for p in sys.argv[2:] if p not in da))
EOF
)
fi
lauf gh release upload "$TAG" -R "$ZIEL" --clobber "$MANIFESTE/pakete.json"

# ---------- 5. freigeben ----------

if [ "$FREIGABE" = 0 ]; then
  echo "$TAG bleibt Vorabfassung (--ohne-freigabe). Freigeben später: gh release edit $TAG -R $ZIEL --prerelease=false --latest"
  exit 0
fi
if [ -n "$FEHLT" ] && [ "$TROTZDEM" = 0 ]; then
  fehler "Im Verzeichnis fehlen: $FEHLT – $TAG bleibt Vorabfassung (mit --trotzdem freigeben oder nachbauen)"
fi
frage "$TAG freigeben? Danach lädt die App es als „latest“."
lauf gh release edit "$TAG" -R "$ZIEL" --prerelease=false --latest
if [ "$TROCKEN" = 1 ]; then echo "(trocken – nichts angelegt, nichts hochgeladen)"; else
  echo "Fertig: https://github.com/$ZIEL/releases/tag/$TAG"
fi
