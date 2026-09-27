#!/usr/bin/env python3
"""Cover uniche per ogni guida → site/covers/guida-<slug>.jpg.

Perché esiste: i pin creati via RSS partono dall'immagine dell'item — se tutti
gli item di uno stesso feed condividono la stessa cover, Pinterest rischia di
deduplicarli e di non pubblicarli. Ogni guida ha quindi una sua immagine in
stile pin (titolo della guida + foto/layour di nicchia).

La cover è DETERMINISTICA: rng seminato sullo slug → rigenerandola non cambia
(e quindi non genera commit inutili). In più viene ricreata solo se la guida
sorgente è più nuova della cover.

Uso:
  python3 tools/build_cover_guide.py          # solo mancanti/aggiornate
  tools/build_cover_guide.py --force          # rigenera tutte
Di solito la chiama tools/routine.py prima del build del sito.
NB: serve PIL + assets/ (fonts e foto) → gira in locale, non in CI.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "guide"
OUT = ROOT / "site" / "covers"
NICCHIA = {"casa": "casa", "cibo": "cibo", "fin": "finanza", "par": "parenting"}

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
import immagini  # noqa: E402
from build_guide import _parse  # noqa: E402


def _sezioni(body: str) -> list[str]:
    """Titoli delle sezioni ## della guida → checklist del layout "lista"."""
    return [r[3:].strip() for r in body.splitlines() if r.startswith("## ")][:6]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    fatte, saltate = 0, 0
    for src in sorted(SRC.glob("*.md")):
        slug = src.stem
        dst = OUT / f"guida-{slug}.jpg"
        if not args.force and dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            saltate += 1
            continue
        meta, body = _parse(src)
        nid = NICCHIA.get(slug.split("-")[0], slug.split("-")[0])
        cfg_p = ROOT / "config" / "nicchie" / f"{nid}.yaml"
        if not cfg_p.exists():
            print(f"  ? {slug}: nicchia '{nid}' sconosciuta, salto")
            continue
        cfg = yaml.safe_load(cfg_p.read_text(encoding="utf-8"))
        titolo = str(meta.get("titolo", slug))
        rng = random.Random(f"cover:{slug}")  # stesso slug → stessa scelta layout/foto
        item = {"id": slug, "titolo": titolo, "kw": []}
        testo = {
            "titolo": titolo,
            "descrizione": str(meta.get("descrizione", "")),
            "overlay": titolo,
            "sottotitolo": str(meta.get("board", "")),
            "passi": _sezioni(body),
        }
        png, _ = immagini.genera_immagine(item, testo, cfg, rng)
        with Image.open(png) as im:
            im.convert("RGB").save(dst, "JPEG", quality=88, optimize=True)
        fatte += 1
        print(f"  ✓ {dst.name}")
    print(f"cover guide: {fatte} create, {saltate} già aggiornate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
