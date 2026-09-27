#!/usr/bin/env python3
"""Scarica foto Pexels per ID (uso commerciale libero, nessuna attribuzione obbligatoria).

Workflow consigliato (Pexels blocca lo scraping automatico con Cloudflare):
  1. cerchi la foto su https://www.pexels.com/search/<query>/
  2. verifichi che la descrizione della pagina corrisponda a quello che vuoi
  3. copi l'ID dalla URL (https://www.pexels.com/photo/<slug>-<ID>)
  4. lo passi qui:

     python3 tools/fetch_pexels.py --nicchia casa --ids 8112993,4992480
     python3 tools/fetch_pexels.py --nicchia cibo --ids 38963909 --desc "pane rustico su tavolo"

I crediti vengono aggiunti automaticamente a assets/backgrounds/<nicchia>/ATTRIBUTI.md
e a assets/backgrounds/CREDITS_PEXELS.json.

Verifica sempre il risultato con una contact sheet:
  python3 tools/sheet.py --nicchia casa
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SFONDI = ROOT / "assets" / "backgrounds"
CREDITS = SFONDI / "CREDITS_PEXELS.json"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
LIC = "Pexels License (uso commerciale libero, nessuna attribuzione obbligatoria)"


def scarica(pid: str) -> tuple[bytes, tuple[int, int]] | None:
    url = (f"https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg"
           f"?auto=compress&cs=tinysrgb&w=1600&q=80")
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=40) as r:
            data = r.read()
        im = Image.open(io.BytesIO(data))
        if im.size[0] < 900:
            print(f"  ! {pid}: troppo piccola {im.size}", file=sys.stderr)
            return None
        return data, im.size
    except Exception as e:  # noqa: BLE001
        print(f"  ! {pid}: {e}", file=sys.stderr)
        return None


def slug(desc: str) -> str:
    return "".join(c for c in desc if c.isalnum())[:28] or "foto"


def aggiungi_crediti(nicchia: str, entries: dict) -> None:
    credits = json.loads(CREDITS.read_text()) if CREDITS.exists() else {}
    credits.update(entries)
    CREDITS.write_text(json.dumps(credits, indent=2, ensure_ascii=False))

    att = SFONDI / nicchia / "ATTRIBUTI.md"
    testo = att.read_text() if att.exists() else f"# Crediti foto — {nicchia}\n"
    for percorso, riga in entries.items():
        line = (f"- `{Path(percorso).name}` — {riga['desc']} · licenza: Pexels · "
                f"fonte: {riga['url']}")
        if Path(percorso).name not in testo:
            testo = testo.rstrip("\n") + "\n" + line + "\n"
    att.write_text(testo)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nicchia", required=True, help="id nicchia (casa, cibo, finanza, parenting)")
    ap.add_argument("--ids", required=True, help="ID separati da virgola (URL: /photo/<slug>-<ID>)")
    ap.add_argument("--desc", default="", help="descrizione (default: ID)")
    args = ap.parse_args()

    out = SFONDI / args.nicchia
    out.mkdir(parents=True, exist_ok=True)
    nuovi: dict = {}
    for pid in [x.strip() for x in args.ids.split(",") if x.strip()]:
        res = scarica(pid)
        if not res:
            continue
        data, (w, h) = res
        desc = args.desc or f"foto pexels {pid}"
        fn = out / f"p{pid}_{slug(desc)}.jpg"
        fn.write_bytes(data)
        print(f"  + {fn.name} {w}x{h} {len(data) // 1024}KB")
        nuovi[str(fn)] = {
            "id": pid, "desc": desc, "w": w, "h": h,
            "url": f"https://www.pexels.com/photo/{pid}/", "licenza": LIC,
        }
    if nuovi:
        aggiungi_crediti(args.nicchia, nuovi)
        print(f"crediti aggiornati (+{len(nuovi)})")
        return 0
    print("nessuna foto scaricata", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
