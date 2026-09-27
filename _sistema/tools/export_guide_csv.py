#!/usr/bin/env python3
"""Piano B: CSV per l'upload manuale delle guide (quando l'RSS non parte).

Pinterest "Crea pin in blocco" accetta anche il caricamento di un CSV: una riga
= un pin, con Title, Media URL (immagine pubblica), board, Description, Link e
Publish date. È la via di riserva quando l'auto-publish da RSS resta fermo.

Genera un CSV per board, con le guide che sono online ma NON ancora pin
(cioè quelle senza `pubblicato:` nel frontmatter e con pagina già pubblicata).

Uso:
  python3 tools/export_guide_csv.py              # tutte le guide in coda
  python3 tools/export_guide_csv.py --dry-run    # mostra le righe, non scrive
  python3 tools/export_guide_csv.py --prese      # segna come pubblicate le guide già nel CSV
                                                  # (Esegui DOPO aver caricato il CSV)
Output: output/csv/guide/board-<slug>.csv (+ guida-pendenti.txt con i nomi file)
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import url_base  # noqa: E402 — radice del sito, fonte unica

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "guide"
OUT = ROOT / "output" / "csv" / "guide"
NICCHIA = {"casa": "casa", "cibo": "cibo", "fin": "finanza", "par": "parenting"}
COLONNE = ["Title", "Media URL", "Pinterest board", "Thumbnail", "Description",
           "Link", "Publish date", "Keywords"]

def _slug(board: str) -> str:
    import re
    s = board.lower()
    for pat, rep in [(r"[àáâä]", "a"), (r"[èéêë]", "e"), (r"[ìíîï]", "i"),
                     (r"[òóôö]", "o"), (r"[ùúûü]", "u")]:
        s = re.sub(pat, rep, s)
    s = s.replace("&", " ")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", "-", s.strip())

def _base() -> str:
    return url_base.site_base(ROOT)

def _meta(path: Path) -> dict:
    t = path.read_text(encoding="utf-8")
    return yaml.safe_load(t.split("---", 2)[1]) if t.startswith("---") else {}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prese", action="store_true",
                    help="dopo l'upload: marca le guide del CSV come pubblicate")
    args = ap.parse_args()

    base = _base()
    oggi = date.today().isoformat()
    righe: dict[str, list[dict]] = {}

    for src in sorted(SRC.glob("*.md")):
        meta = _meta(src)
        slug = src.stem
        if meta.get("pubblicato"):
            continue
        dal = str(meta.get("pubblica_dal") or "")
        if dal and dal > oggi:
            continue  # ancora in programma
        if not (ROOT / "site" / "guide" / f"{slug}.html").exists():
            continue  # pagina non ancora online
        board = str(meta.get("board") or "")
        if not board:
            continue
        righe.setdefault(board, []).append({
            "Title": str(meta.get("titolo", slug)),
            "Media URL": f"{base}covers/guida-{slug}.jpg",
            "Pinterest board": board,
            "Thumbnail": f"{base}covers/guida-{slug}.jpg",
            "Description": str(meta.get("descrizione", "")),
            "Link": f"{base}guide/{slug}.html",
            "Publish date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "Keywords": ", ".join(str(k) for k in (meta.get("kw") or [])),
            "_slug": slug,
        })

    if not righe:
        print("Nessuna guida da caricare: coda vuota (tutto già pubblicato o in programma).")
        return 0

    totale = sum(len(v) for v in righe.values())
    if args.dry_run:
        for board, voci in sorted(righe.items()):
            print(f"\n{board} ({len(voci)} pin)")
            for r in voci:
                print(f"  {r['_slug']}: «{r['Title']}»")
                print(f"      img  {r['Media URL']}")
                print(f"      link {r['Link']}")
        print(f"\nTOTALE {totale} pin pronti in {len(righe)} board (dry-run, nessun file scritto)")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    scritti: list[str] = []
    for board, voci in sorted(righe.items()):
        dst = OUT / f"board-{_slug(board)}.csv"
        with dst.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLONNE, extrasaction="ignore")
            w.writeheader()
            w.writerows(voci)
        scritti.append(dst.name)
        print(f"  {dst.name}: {len(voci)} pin → board «{board}»")

    elenco = OUT / "guida-pendenti.txt"
    elenco.write_text("\n".join(sorted(r["_slug"] for v in righe.values() for r in v)) + "\n",
                      encoding="utf-8")
    print(f"\n{totale} pin in {len(scritti)} CSV: {OUT}")
    print(f"caricali da Pinterest → Crea pin in blocco → Carica CSV (un file per volta)")
    print(f"dopo l'upload:  python3 tools/export_guide_csv.py --prese   (svuota la coda)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
