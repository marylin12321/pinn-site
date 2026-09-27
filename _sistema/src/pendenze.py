#!/usr/bin/env python3
"""La coda di pubblicazione: guide online che Pinterest non ha ancora come pin.

Unica fonte di verità per tre usi diversi:
  1. feed RSS   (tools/build_feed.py)  → cosa offre a Pinterest
  2. CSV        (tools/export_guide_csv.py) → piano B upload manuale
  3. API v5     (tools/pinterest_api.py) → post automatico

Una guida è "in coda" se:
  - ha un `board` (altrimenti non c'è dove pubblicarla)
  - non ha `pubblicato:` (cioè non è già un pin)
  - la sua data di rilascio (`pubblica_dal`) è passata o assente
  - la pagina esiste già in site/guide/ (mai linkare una pagina 404)

Uso tipico:
  from pendenze import coda
  for voce in coda():
      print(voce["slug"], voce["board"], voce["titolo"])
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import url_base
import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "guide"
NICCHIA = {"casa": "casa", "cibo": "cibo", "fin": "finanza", "par": "parenting"}


def _slug(board: str) -> str:
    import re
    s = board.lower()
    for pat, rep in [(r"[àáâä]", "a"), (r"[èéêë]", "e"), (r"[ìíîï]", "i"),
                     (r"[òóôö]", "o"), (r"[ùúûü]", "u")]:
        s = re.sub(pat, rep, s)
    s = s.replace("&", " ")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", "-", s.strip())


def _meta(path: Path) -> dict:
    t = path.read_text(encoding="utf-8")
    return (yaml.safe_load(t.split("---", 2)[1]) or {}) if t.startswith("---") else {}


def base_url() -> str:
    """Radice pubblica del sito (unica fonte: config/system.yaml)."""
    return url_base.site_base(ROOT)


def handle(nid: str) -> str:
    p = ROOT / "config" / "nicchie" / f"{nid}.yaml"
    if not p.exists():
        return ""
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return str((cfg.get("nicchia") or {}).get("handle") or "").lstrip("@")


def coda(nid: str | None = None) -> list[dict]:
    """Guide in coda di pubblicazione, dalla più recente alla più vecchia."""
    base = base_url()
    oggi = date.today().isoformat()
    out: list[tuple[float, dict]] = []
    for src in sorted(SRC.glob("*.md")):
        slug = src.stem
        nicchia = NICCHIA.get(slug.split("-")[0], slug.split("-")[0])
        if nid and nicchia != nid:
            continue
        meta = _meta(src)
        board = str(meta.get("board") or "")
        if not board or meta.get("pubblicato"):
            continue
        dal = str(meta.get("pubblica_dal") or "")
        if dal and dal > oggi:
            continue  # ancora in programma
        if not (ROOT / "site" / "guide" / f"{slug}.html").exists():
            continue  # pagina non ancora online: non si linka il 404
        ts = (datetime.fromisoformat(dal).timestamp() if dal else src.stat().st_mtime)
        out.append((ts, {
            "slug": slug, "nicchia": nicchia, "board": board,
            "titolo": str(meta.get("titolo", slug)),
            "descrizione": str(meta.get("descrizione", "")),
            "link": f"{base}guide/{slug}.html",
            "immagine": f"{base}covers/guida-{slug}.jpg",
            "cover_esiste": (ROOT / "site" / "covers" / f"guida-{slug}.jpg").exists(),
        }))
    out.sort(key=lambda v: v[0], reverse=True)
    return [v for _, v in out]


def segna_pubblicata(slug: str, giorno: str | None = None) -> bool:
    """Scrive `pubblicato: YYYY-MM-DD` nel frontmatter. Ritorna True se cambiata.

    Va chiamata DOPO che il pin è davvero online: è questo campo che toglie la
    guida dal feed RSS e dalla coda, così non si duplica nulla.
    """
    p = SRC / f"{slug}.md"
    if not p.exists():
        return False
    giorno = giorno or date.today().isoformat()
    t = p.read_text(encoding="utf-8")
    if "pubblicato:" in t:
        return False
    parti = t.split("---", 2)
    if len(parti) < 3:  # frontmatter senza chiusura (non dovrebbe accadere)
        return False
    nuovo = f"---{parti[1].rstrip()}\npubblicato: {giorno}\n---{parti[2]}"
    p.write_text(nuovo, encoding="utf-8")
    return True
