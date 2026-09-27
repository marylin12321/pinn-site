#!/usr/bin/env python3
"""Genera una contact sheet per curare visivamente le foto di una nicchia.

  python3 tools/sheet.py --nicchia casa           # sheet di assets/backgrounds/casa
  python3 tools/sheet.py --cartella output/x      # cartella arbitraria

Le celle sono numerate: usa gli indici per decidere cosa tenere/eliminare.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True
ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nicchia", help="id nicchia")
    ap.add_argument("--cartella", help="cartella arbitraria con immagini")
    ap.add_argument("--out", help="path output (default: output/sheet_<nome>.png)")
    args = ap.parse_args()

    if args.cartella:
        src = Path(args.cartella)
    elif args.nicchia:
        src = ROOT / "assets" / "backgrounds" / args.nicchia
    else:
        ap.error("serve --nicchia o --cartella")

    files = sorted(p for p in src.iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    if not files:
        print("nessuna immagine")
        return 1

    try:
        font = ImageFont.truetype(str(ROOT / "assets/fonts/Poppins-Bold.ttf"), 44)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()

    cell, cols = (480, 320), 4
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell[0], rows * cell[1]), (20, 20, 20))
    dr = ImageDraw.Draw(sheet)
    for i, p in enumerate(files):
        im = Image.open(p).convert("RGB")
        r = max(cell[0] / im.width, cell[1] / im.height)
        im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
        l, t = (im.width - cell[0]) // 2, (im.height - cell[1]) // 2
        im = im.crop((l, t, l + cell[0], t + cell[1]))
        x, y = (i % cols) * cell[0], (i // cols) * cell[1]
        sheet.paste(im, (x, y))
        dr.rectangle([x + 6, y + 6, x + 64, y + 64], fill=(0, 0, 0))
        dr.text((x + 16, y + 8), str(i + 1), fill=(255, 230, 0), font=font)

    dst = Path(args.out) if args.out else ROOT / "output" / f"sheet_{src.name}.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dst)
    print(f"{dst}  ({len(files)} foto, {sheet.size[0]}x{sheet.size[1]})")
    for i, p in enumerate(files, 1):
        print(f"  {i:2} {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
