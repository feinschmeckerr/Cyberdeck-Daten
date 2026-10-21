"""Packt die Details eines Landes für die PiFlux-App: jede Datei einzeln gzip-komprimiert, über 1,9 GB geteilt
(Grenze je Release-Datei 2 GB), dazu das Manifest <land>.json mit Größen und sha256 – vor und nach dem Packen.

    python3 werkzeuge/packen.py <land> <ordner mit den Ergebnissen> <ausgabeordner>

Im Ergebnisordner liegt, was die Erzeuger des PiFlux für dieses Land schreiben (suchindex.sqlite, suchwoerter.sqlite,
merkmale.sqlite, gebaeude.mbtiles, strassennetz/…). Pfade im Manifest sind relativ zu kartendaten/ in der App.
"""

import gzip
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

TEIL = 1_900_000_000
PUFFER = 8 * 1024 * 1024


def sha256(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as datei:
        while block := datei.read(PUFFER):
            h.update(block)
    return h.hexdigest()


def packen(land, quelle, ausgabe):
    ausgabe.mkdir(parents=True, exist_ok=True)
    dateien = []
    for pfad in sorted(p for p in quelle.rglob("*") if p.is_file()):
        relativ = pfad.relative_to(quelle).as_posix()
        name = f"{land}--{relativ.replace('/', '--')}.gz"
        gepackt = ausgabe / name
        with open(pfad, "rb") as roh, gzip.open(gepackt, "wb", compresslevel=6) as ziel:
            shutil.copyfileobj(roh, ziel, PUFFER)
        eintrag = {"pfad": relativ, "groesse": pfad.stat().st_size, "sha256": sha256(pfad),
                   "gz_groesse": gepackt.stat().st_size, "gz_sha256": sha256(gepackt)}
        if gepackt.stat().st_size > TEIL:
            teile = []
            with open(gepackt, "rb") as ganz:
                nummer = 1
                while block := ganz.read(TEIL):
                    teil = ausgabe / f"{name}.teil{nummer}"
                    teil.write_bytes(block)
                    teile.append({"name": teil.name, "groesse": len(block), "sha256": hashlib.sha256(block).hexdigest()})
                    nummer += 1
            gepackt.unlink()
            eintrag["teile"] = teile
        else:
            eintrag["name"] = name
        dateien.append(eintrag)
        print(f"  {relativ}: {eintrag['groesse'] / 1e6:.1f} MB → {eintrag['gz_groesse'] / 1e6:.1f} MB", flush=True)
    manifest = {"land": land, "stand": time.strftime("%Y-%m-%d", time.gmtime()), "dateien": dateien,
                "groesse": sum(d["groesse"] for d in dateien), "gz_groesse": sum(d["gz_groesse"] for d in dateien)}
    (ausgabe / f"{land}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    m = packen(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
    print(f"{m['land']}: {len(m['dateien'])} Dateien, {m['groesse'] / 1e9:.2f} GB → {m['gz_groesse'] / 1e9:.2f} GB")
