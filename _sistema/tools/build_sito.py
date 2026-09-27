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
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import build_guide
import build_landing
import build_feed
import lint_guide

ROOT = Path(__file__).resolve().parent.parent


def _site_base() -> str:
    """Radice sito derivata dai media_base_url (…/pin → …/)."""
    for nid in ["casa", "cibo", "finanza", "parenting"]:
        cfg = yaml.safe_load((ROOT / "config" / "nicchie" / f"{nid}.yaml").read_text(encoding="utf-8"))
        base = (cfg.get("media_base_url") or "").strip().rstrip("/")
        if base:
            return base.rsplit("/", 1)[0] + "/"
    return "https://example.com/pinn-site/"


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


def _check_ritmo() -> bool:
    """Niente più di N guide a settimana per account (anti-burst, ritmo sandbox).

    Il tetto si applica alle settimane non ancora concluse: la storia passata
    non viene più toccata, ma da oggi in poi nessuna settimana può superarlo.
    """
    from datetime import timedelta

    sistema = yaml.safe_load((ROOT / "config" / "system.yaml").read_text(encoding="utf-8")) or {}
    max_per_sett = int(((sistema.get("regole") or {}).get("guide_settimana_max")) or 2)
    oggi = date.today()
    iso_oggi = oggi.isocalendar()
    lunedi_oggi = oggi - timedelta(days=iso_oggi[2] - 1)
    buckets: dict[tuple[str, str], list[str]] = {}
    for src in sorted((ROOT / "content" / "guide").glob("*.md")):
        text = src.read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else {}
        giorno = str((meta or {}).get("pubblica_dal") or "") or date.fromtimestamp(
            src.stat().st_mtime).isoformat()
        try:
            dt = date.fromisoformat(giorno)
        except ValueError:
            continue
        iso = dt.isocalendar()
        inizio = dt - timedelta(days=iso[2] - 1)
        if inizio + timedelta(days=6) < oggi:
            continue  # settimana conclusa: la storia non si tocca
        prefisso = src.stem.split("-")[0]
        nid = build_guide.NICCHIA_PER_PREFISSO.get(prefisso, prefisso)
        buckets.setdefault((nid, f"{iso[0]}-W{iso[1]:02d}"), []).append(f"{src.stem} ({giorno})")
    ok = True
    for (nid, settimana), voci in sorted(buckets.items()):
        if len(voci) <= max_per_sett:
            continue
        anno, num_sett = settimana.split("-W")
        inizio_sett = date.fromisocalendar(int(anno), int(num_sett), 1)
        if inizio_sett == lunedi_oggi:
            # settimana in corso (es. quella del lancio): avvisa, non bloccare
            print(f"CHECK ⚠ ritmo: {nid} {settimana} = {len(voci)} guide già in corso "
                  f"(tetto {max_per_sett}): " + ", ".join(sorted(voci)))
            continue
        print(f"CHECK ✗ ritmo: {nid} {settimana} = {len(voci)} guide (tetto {max_per_sett}): "
              + ", ".join(sorted(voci)))
        ok = False
    if ok:
        print(f"CHECK ✓ ritmo: nessuna settimana futura oltre {max_per_sett} guide per account")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    build_landing.genera()
    guide = build_guide.genera()
    feeds = build_feed.genera()
    base = _site_base()
    sm = _sitemap(guide, base)
    print(f"sitemap: {sm.relative_to(ROOT)} + robots.txt (base {base})")

    if args.check:
        ok = True
        idx = ROOT / "site" / "index.html"
        if "guide/" not in idx.read_text(encoding="utf-8"):
            print("CHECK ✗ landing senza link alle guide")
            ok = False
        if not build_feed.check():
            ok = False
        if not _check_ritmo():
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
