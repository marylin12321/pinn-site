#!/usr/bin/env python3
"""Genera i feed RSS 2.0 per la pubblicazione automatica Pinterest (uno per bacheca).

Sorgenti: content/guide/*.md (frontmatter board:, pubblica_dal:) + config/nicchie/*.yaml.
Output: site/feed-<nid>-<boardslug>.xml — solo per le board che hanno guide pubblicabili
oggi (guida con pubblica_dal futuro resta fuori dal feed finché non arriva la data).

Pinterest crea i pin da solo entro 24h (max 200/giorno): titolo/descrizione dagli
item, immagine da <enclosure>/<media:content> (cover di nicchia), link alla guida
(sul dominio verificato — prerequisito, vedi docs/05-operazioni.md).
Collegamento una tantum: Impostazioni → Crea Pin in blocco → Collega feed RSS.

Uso:
  python3 tools/build_feed.py            # (di solito via tools/build_sito.py)
  python3 tools/build_feed.py --check    # valida XML + slug board vs Pinterest
"""
from __future__ import annotations

import argparse
import email.utils
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "guide"
SITE = ROOT / "site"


def slug_board(board: str) -> str:
    """Slug stile Pinterest: minuscole, spazi→trattini, & e speciali via.
    Verificato contro gli slug live (es. 'Pulizie & Routine' → 'pulizie-routine')."""
    s = board.lower()
    s = re.sub(r"[àáâä]", "a", s)
    s = re.sub(r"[èéêë]", "e", s)
    s = re.sub(r"[ìíîï]", "i", s)
    s = re.sub(r"[òóôö]", "o", s)
    s = re.sub(r"[ùúûü]", "u", s)
    s = s.replace("&", " ")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", "-", s.strip())


def _site_base() -> str:
    for nid in ["casa", "cibo", "finanza", "parenting"]:
        cfg = yaml.safe_load((ROOT / "config" / "nicchie" / f"{nid}.yaml").read_text(encoding="utf-8"))
        base = (cfg.get("media_base_url") or "").strip().rstrip("/")
        if base:
            return base.rsplit("/", 1)[0] + "/"
    return "https://example.com/pinn-site/"


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def genera() -> list[Path]:
    base = _site_base()
    from datetime import date, datetime, timezone

    oggi = date.today().isoformat()
    # raggruppa guide per (nicchia, board) — SOLO quelle pubblicabili oggi:
    # `pubblica_dal` futuro = fuori dal feed (altrimenti Pinterest le posta in anticipo)
    gruppi: dict[tuple[str, str], list[Path]] = {}
    for src in sorted(SRC.glob("*.md")):
        nid = {"casa": "casa", "cibo": "cibo", "fin": "finanza", "par": "parenting"}.get(
            src.stem.split("-")[0], src.stem.split("-")[0])
        text = src.read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else {}
        board = (meta or {}).get("board", "")
        dal = str((meta or {}).get("pubblica_dal") or "")
        if board and not (dal and dal > oggi):
            gruppi.setdefault((nid, board), []).append(src)
    scritti: list[Path] = []
    for (nid, board), files in sorted(gruppi.items()):
        # ordine RSS corretto: dal più RECENTE al più vecchio (i lettori leggono dall'alto,
        # Pinterest prende di fatto il primo item → deve sempre essere l'ultimo rilascio)
        voci: list[tuple[float, Path, dict]] = []
        for src in files:
            text = src.read_text(encoding="utf-8")
            meta = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else {}
            dal = str((meta or {}).get("pubblica_dal") or "")
            if dal:
                # data di rilascio reale, non la mtime (creata giorni prima)
                ts = datetime.fromisoformat(dal).replace(tzinfo=timezone.utc).timestamp()
            else:
                ts = src.stat().st_mtime
            voci.append((ts, src, meta or {}))
        voci.sort(key=lambda v: (v[0], v[1].name), reverse=True)

        items = []
        ultimo = 0.0
        for ts, src, meta in voci:
            titolo = meta.get("titolo", src.stem)
            descr = meta.get("descrizione", "")
            url = f"{base}guide/{src.stem}.html"
            pub = email.utils.formatdate(ts, usegmt=True)
            # cover UNICA per guida (in locale la genera build_cover_guide.py):
            # se tutti gli item dello stesso feed hanno la stessa immagine,
            # Pinterest rischia di deduplicarli e di non postarli mai
            cover_propria = SITE / "covers" / f"guida-{src.stem}.jpg"
            cover = (f"{base}covers/guida-{src.stem}.jpg" if cover_propria.exists()
                     else f"{base}covers/{nid}.jpg")
            ultimo = max(ultimo, ts)
            items.append(
                f"    <item>\n      <title>{_esc(titolo)}</title>\n"
                f"      <link>{url}</link>\n      <guid isPermaLink=\"true\">{url}</guid>\n"
                f"      <description>{_esc(descr)}</description>\n"
                f"      <pubDate>{pub}</pubDate>\n"
                f"      <enclosure url=\"{cover}\" type=\"image/jpeg\" />\n"
                f"      <media:content url=\"{cover}\" medium=\"image\" type=\"image/jpeg\" />\n"
                f"    </item>"
            )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">\n'
            f"  <channel>\n    <title>Quattro Mondi — {_esc(board)}</title>\n"
            f"    <link>{base}guide/</link>\n"
            f"    <description>Guide {_esc(board)} (Quattro Mondi)</description>\n"
            f"    <language>it-it</language>\n"
            f"    <lastBuildDate>{email.utils.formatdate(ultimo, usegmt=True)}</lastBuildDate>\n"
            + "\n".join(items)
            + "\n  </channel>\n</rss>\n"
        )
        dst = SITE / f"feed-{nid}-{slug_board(board)}.xml"
        dst.write_text(xml, encoding="utf-8")
        scritti.append(dst)
    print(f"feed: {len(scritti)} file (uno per bacheca con guide)")
    return scritti


def check() -> bool:
    ok = True
    for xml in sorted(SITE.glob("feed-*.xml")):
        try:
            root = ET.parse(str(xml)).getroot()
            items = root.findall("./channel/item")
            if not items:
                print(f"CHECK ✗ {xml.name}: nessun item")
                ok = False
                continue
            for it in items:
                for tag in ("title", "link", "description"):
                    el = it.find(tag)
                    if el is None or not (el.text or "").strip():
                        print(f"CHECK ✗ {xml.name}: item senza <{tag}>")
                        ok = False
                enc = it.find("enclosure")
                if enc is None or not (enc.get("url") or "").startswith("https://"):
                    print(f"CHECK ✗ {xml.name}: enclosure non https")
                    ok = False
                link = (it.findtext("link") or "")
                if "guide/" not in link:
                    print(f"CHECK ✗ {xml.name}: link fuori dal dominio guide")
                    ok = False
        except ET.ParseError as e:
            print(f"CHECK ✗ {xml.name}: XML non valido ({e})")
            ok = False
    # slug board: devono esistere nei config
    boards_cfg = set()
    for nid in ["casa", "cibo", "finanza", "parenting"]:
        cfg = yaml.safe_load((ROOT / "config" / "nicchie" / f"{nid}.yaml").read_text(encoding="utf-8"))
        for b in cfg["nicchia"].get("boards") or []:
            boards_cfg.add(slug_board(b))
    for xml in SITE.glob("feed-*.xml"):
        slug = xml.stem.split("-", 2)[-1]
        if slug not in boards_cfg:
            print(f"CHECK ✗ {xml.name}: slug '{slug}' non corrisponde a nessuna board")
            ok = False
    # guide FUTURE non devono comparire in nessun feed (Pinterest le posterebbe subito)
    from datetime import date

    oggi = date.today().isoformat()
    future = set()
    for src in SRC.glob("*.md"):
        text = src.read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else {}
        dal = str((meta or {}).get("pubblica_dal") or "")
        if dal and dal > oggi:
            future.add(src.stem)
    for xml in SITE.glob("feed-*.xml"):
        testo = xml.read_text(encoding="utf-8")
        for slug_futuro in sorted(future):
            if f"guide/{slug_futuro}.html" in testo:
                print(f"CHECK ✗ {xml.name}: contiene la guida futura {slug_futuro}")
                ok = False
    if ok:
        print("CHECK ✓ feed validi, slug board coerenti, niente guide future")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    genera()
    if args.check and not check():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
