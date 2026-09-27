#!/usr/bin/env python3
"""Cover uniche per ogni guida → site/covers/guida-<slug>.jpg.

Perché esiste: i pin creati via RSS partono dall'immagine dell'item — se tutti
gli item di uno stesso feed condividono la stessa cover, Pinterest rischia di
deduplicarli e di non pubblicarli. Ogni guida ha quindi una sua immagine in
stile pin (titolo della guida + foto/layour di nicchia).

La cover è DETERMINISTICA: rng seminato sullo slug → rigenerandola non cambia
(e quindi non genera commit inutili). In più viene ricreata solo se la guida
sorgente è più nuova della cover.

Sul perché della `foto:` nel frontmatter: il rng da solo NON bastava. La foto
usciva da `rng.choice` sulla cartella degli sfondi della nicchia, quindi la
scelta dipendeva da quanti file ci erano: aggiungere le foto per le 7 guide
nuove ha spostato la scelta di 37 guide su 40 (misurato il 27/09/2026).
Ora ogni guida porta `foto: <file>.jpg` nel frontmatter e la scelta è ferma:
le cover si possono rigenerare per sempre senza che cambi la foto.

Uso:
  python3 tools/build_cover_guide.py                  # solo mancanti/aggiornate
  tools/build_cover_guide.py --force                  # rigenera tutte
  tools/build_cover_guide.py --registra-sfondi --force  # fissa la foto mancante
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


def _scrive_foto(src: Path, foto: str) -> bool:
    """Scrive `foto: <file>` nel frontmatter. True se il file è cambiato.

    Tiene la chiave subito dopo `descrizione` così il frontmatter resta
    leggibile; se il frontmatter non c'è non lo invento (una guida senza
    frontmatter non è una guida valida e va segnalata, non sistemata qui).
    """
    testo = src.read_text(encoding="utf-8")
    if not testo.startswith("---"):
        print(f"  ! {src.stem}: nessun frontmatter, non posso fissare la foto")
        return False
    _, fm, resto = testo.split("---", 2)
    righe = fm.rstrip("\n").split("\n")
    fuori = [i for i, l in enumerate(righe) if l.startswith("foto:")]
    for i in fuori:
        del righe[i]
    inserisco = dopo = False
    for i, l in enumerate(righe):
        if l.startswith("descrizione:"):
            dopo = True
        elif dopo and l and not l.startswith((" ", "\t", "-")):
            righe.insert(i, f"foto: {foto}")
            inserisco = True
            break
    if not inserisco:
        righe.append(f"foto: {foto}")
    nuovo = "---\n" + "\n".join(righe) + "\n---" + resto
    if nuovo == testo:
        return False
    src.write_text(nuovo, encoding="utf-8")
    return True


def _sezioni(body: str) -> list[str]:
    """Titoli delle sezioni ## della guida → checklist del layout "lista"."""
    return [r[3:].strip() for r in body.splitlines() if r.startswith("## ")][:6]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--registra-sfondi", action="store_true",
                    help="scrive foto: nel frontmatter delle guide che non l'hanno "
                         "(da usare con --force: fissa la scelta attuale)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    fatte, saltate, fissate = 0, 0, 0
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
        rng = random.Random(f"cover:{slug}")  # stesso slug → stessa scelta layout
        item = {"id": slug, "titolo": titolo, "kw": []}
        if meta.get("foto"):
            item["foto"] = str(meta["foto"])  # foto fermata: non cambia al rigenerare
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
        if args.registra_sfondi and not meta.get("foto"):
            scelta = immagini.sfondi_scelti().get(slug)
            if scelta and _scrive_foto(src, scelta):
                fissate += 1
        fatte += 1
        print(f"  ✓ {dst.name}")
    msg = f"cover guide: {fatte} create, {saltate} già aggiornate"
    if fissate:
        msg += f", {fissate} sfondi fissati nel frontmatter"
    print(msg)
    if args.registra_sfondi and fissate:
        print("  NB: le guide toccate hanno il mtime più nuovo delle cover → il prossimo")
        print("      build le rigenera. Senza --force è un solo giro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
