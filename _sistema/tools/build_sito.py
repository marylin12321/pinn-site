#!/usr/bin/env python3
"""Ricostruisce l'INTERO sito da zero (un solo comando, accumulo automatico).

  python3 tools/build_sito.py              # landing + guide + indice + sitemap + robots
  python3 tools/build_sito.py --check      # + validazioni

Sorgenti (fonte unica): config/nicchie/*.yaml + content/guide/*.md + site/privacy.html.
Output: site/ (pronto per tools/pubblica_immagini.py).
Ogni run accumula: nuove guide compaiono da sole, link/prodotti si aggiornano,
le URL non cambiano mai (stabilità per i pin già pubblicati).
"""
from __future__ import annotations

import argparse
from datetime import date
import sys
from pathlib import Path

import yaml

import build_guide
import build_landing
import build_feed
import lint_guide
import build_printable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import url_base  # noqa: E402 — radice del sito, fonte unica

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

def _site_base() -> str:
    """Radice pubblica del sito (unica fonte: config/system.yaml)."""
    return url_base.site_base(ROOT)

def _sitemap(pagine: list[Path], base: str) -> Path:
    oggi = date.today().isoformat()
    urls = ["", "privacy.html", "guide/", "guide/index.html"]
    urls += [f"guide/{p.stem}.html" for p in pagine]
    body = "\n".join(
        f'  <url><loc>{base}{u}</loc><lastmod>{oggi}</lastmod></url>' for u in urls
    )
    dst = ROOT / "site" / "sitemap.xml"
    dst.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n',
        encoding="utf-8",
    )
    (ROOT / "site" / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {base}sitemap.xml\n", encoding="utf-8"
    )
    return dst

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    build_landing.genera()
    guide = build_guide.genera()
    feeds = build_feed.genera()
    printabili = build_printable.genera()
    base = _site_base()
    pag = guide + [SITE / "printable" / f"{s['slug']}.html" for s in printabili]
    sm = _sitemap(pag, base)
    print(f"sitemap: {sm.relative_to(ROOT)} + robots.txt (base {base})")

    if args.check:
        ok = True
        idx = ROOT / "site" / "index.html"
        if "guide/" not in idx.read_text(encoding="utf-8"):
            print("CHECK ✗ landing senza link alle guide")
            ok = False
        if not build_feed.check():
            ok = False
        if not lint_guide.check():
            ok = False
        for g in guide:
            html = g.read_text(encoding="utf-8")
            if "#adv" not in html or "amazon.it/dp" not in html and "Prodotti citati" in html:
                print(f"CHECK ✗ {g.name}: disclosure/prodotti incoerenti")
                ok = False
        # ogni guida deve avere almeno i prodotti del frontmatter o zero card (mai rotte)
        print(f"CHECK ✓ sito completo: landing + {len(guide)} guide + sitemap" if ok else "CHECK FALLITO")
        return 0 if ok else 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
