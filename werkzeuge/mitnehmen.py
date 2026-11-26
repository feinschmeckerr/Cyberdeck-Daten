"""Nimmt Pakete (Zusatzpakete wie Welt, Fahrplan, 3D-Dächer und Länder, die ein Lauf nicht neu gebaut hat) aus dem
bisherigen Release in ein neues mit – bevor das neue „latest“ wird (G-021). Sonst fehlten sie dem neuen Release und die
App meldete sie „nicht mehr im Verzeichnis“.

Je Paket: fehlt es dem neuen Release und hat das bisherige (gh release view: „latest“) sein Manifest <paket>.json,
werden die Dateien aus dem Manifest einzeln geladen, mit Größe und sha256 des Manifests geprüft, hochgeladen und
gelöscht (wenig Platte); das Manifest kommt zuletzt – ein Manifest steht nur im Release, wenn alle Dateien da sind.
Ein Paket, das das bisherige Release nicht hat, wird übergangen. Jeder andere Fehler bricht ab (Ausgang 1), damit das
neue Release nicht unvollständig freigegeben wird.

    python3 werkzeuge/mitnehmen.py <neues-tag> [paket …]   (Repo aus GITHUB_REPOSITORY; ohne Pakete: PAKETE)

Aufgerufen von werkzeuge/release.sh (für alles, was der Daten-Lauf nicht gebaut hat – auch Länder).
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PAKETE = ("welt", "weltosm", "oepnv", "lod2-berlin", "lod2-brandenburg")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")  # Release-Dateien: ohne Pfad und ohne Glob-Zeichen
VERSUCHE = 2
HOCHLADEN_VERSUCHE = 4  # ein Netzfehler bei einer von Hunderten Dateien soll nicht den ganzen Lauf abbrechen
WARTEN_S = 15


def gh(*argumente):
    return subprocess.run(["gh", *argumente], check=True, capture_output=True, text=True).stdout


def dateien(manifest):
    """Release-Dateien eines Manifests: [(name, groesse, sha256)] – gepackte Datei oder ihre Teile (packen.py)."""
    ergebnis = []
    for datei in manifest["dateien"]:
        if datei.get("teile"):
            ergebnis += [(t["name"], int(t["groesse"]), t["sha256"]) for t in datei["teile"]]
        else:
            ergebnis.append((datei["name"], int(datei["gz_groesse"]), datei["gz_sha256"]))
    for name, _groesse, _sha in ergebnis:
        if not NAME.match(name):
            raise ValueError(f"unerwarteter Dateiname im Manifest: {name!r}")
    return ergebnis


def sha256(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as datei:
        while block := datei.read(8 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def namen(tag, repo):
    return set(groessen(tag, repo))


def groessen(tag, repo):
    """Release-Dateien mit Größe: {name: bytes}."""
    zeilen = gh("release", "view", tag, "-R", repo, "--json", "assets", "-q", '.assets[] | "\\(.name) \\(.size)"')
    return {name: int(groesse) for name, groesse in (z.rsplit(" ", 1) for z in zeilen.split("\n") if z.strip())}


def hochladen(tag, repo, pfad):
    """Lädt eine Datei hoch; bei einem Fehler bis zu HOCHLADEN_VERSUCHE Mal mit wachsender Pause."""
    for versuch in range(1, HOCHLADEN_VERSUCHE + 1):
        try:
            return gh("release", "upload", tag, "-R", repo, "--clobber", str(pfad))
        except subprocess.CalledProcessError as fehler:
            if versuch == HOCHLADEN_VERSUCHE:
                raise
            grund = (fehler.stderr or "").strip().splitlines()[-1:] or ["?"]
            print(f"  {pfad.name}: Hochladen gescheitert ({grund[0]}), Versuch {versuch + 1} in {WARTEN_S * versuch} s",
                  flush=True)
            time.sleep(WARTEN_S * versuch)


def laden(tag, repo, name, ordner):
    ziel = ordner / name
    ziel.unlink(missing_ok=True)
    gh("release", "download", tag, "-R", repo, "-D", str(ordner), "--pattern", name)
    return ziel


def mitnehmen(paket, alt, neu, repo, ordner, alt_namen, schon_da=None):
    manifest_name = f"{paket}.json"
    manifest_pfad = laden(alt, repo, manifest_name, ordner)
    manifest = json.loads(manifest_pfad.read_text(encoding="utf-8"))
    liste = dateien(manifest)
    fehlen = [name for name, _g, _s in liste if name not in alt_namen]
    if fehlen:
        raise RuntimeError(f"{paket}: in {alt} fehlen Dateien des Manifests: {', '.join(fehlen)}")
    schon_da = schon_da or {}
    for name, groesse, soll in liste:
        if schon_da.get(name) == groesse:  # nach einem Abbruch (release.sh --tag) nicht noch einmal laden
            print(f"  {name}: schon in {neu}", flush=True)
            continue
        for versuch in range(1, VERSUCHE + 1):
            pfad = laden(alt, repo, name, ordner)
            if pfad.stat().st_size == groesse and sha256(pfad) == soll:
                break
            print(f"  {name}: Prüfsumme passt nicht (Versuch {versuch})", flush=True)
            pfad.unlink()
        else:
            raise RuntimeError(f"{paket}: {name} passt nicht zum Manifest (wird {alt} gerade neu beschrieben?)")
        hochladen(neu, repo, pfad)
        pfad.unlink()
        print(f"  {name}: {groesse / 1e6:.1f} MB", flush=True)
    hochladen(neu, repo, manifest_pfad)
    manifest_pfad.unlink()
    return len(liste)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    neu, pakete = sys.argv[1], sys.argv[2:] or list(PAKETE)
    repo = os.environ["GITHUB_REPOSITORY"]
    try:
        alt = gh("release", "view", "-R", repo, "--json", "tagName", "-q", ".tagName").strip()
    except subprocess.CalledProcessError:
        alt = ""
    if not alt or alt == neu:
        print("Kein bisheriges Release – nichts mitzunehmen")
        return 0
    alt_namen, neu_groessen = namen(alt, repo), groessen(neu, repo)
    neu_namen = set(neu_groessen)
    with tempfile.TemporaryDirectory() as ordner:
        for paket in pakete:
            if f"{paket}.json" in neu_namen:
                print(f"{paket}: schon in {neu}")
            elif f"{paket}.json" not in alt_namen:
                print(f"{paket}: nicht in {alt} – übergangen")
            else:
                print(f"{paket}: aus {alt} nach {neu}", flush=True)
                anzahl = mitnehmen(paket, alt, neu, repo, Path(ordner), alt_namen, neu_groessen)
                print(f"{paket}: {anzahl} Dateien und Manifest mitgenommen", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (subprocess.CalledProcessError, RuntimeError, ValueError, KeyError, OSError) as fehler:
        ausgabe = getattr(fehler, "stderr", "") or ""
        print(f"FEHLER: Mitnehmen gescheitert: {fehler} {ausgabe.strip()}", flush=True)
        sys.exit(1)
