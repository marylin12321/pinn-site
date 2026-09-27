#!/usr/bin/env python3
"""Genera le pagine guida (site/guide/*.html) + indice (site/guide/index.html).

Sorgenti: content/guide/<item_id>.md (testi scritti a mano) + config/nicchie/*.yaml
(prodotti citati, presi per id dal frontmatter: titolo+link+tag dal config).
Ogni rebuild accumula: nuove guide compaiono da sole, link/prodotti si aggiornano.

Formato md:
  ---
  titolo: ... | descrizione: ... | board: ... | prodotti: [casa-p01, ...]
  ---
  Testo con ## h2, **bold**, paragrafi e liste "- ".
"""
from __future__ import annotations

import html as _html
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "guide"
DST = ROOT / "site" / "guide"
# gli slug guida sono gli item id (casa-c01…): i prefissi non sempre = id nicchia
NICCHIA_PER_PREFISSO = {"casa": "casa", "cibo": "cibo", "fin": "finanza", "par": "parenting"}

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
       Helvetica, Arial, sans-serif; color: #2E2A26; line-height: 1.7; background: #F4F1EA; }
.wrap { max-width: 640px; margin: 0 auto; padding: 26px 18px 52px; }
.crumb { font-size: 13.5px; font-weight: 600; color: #6b6259; text-decoration: none; }
.card { background: #fff; border-radius: 20px; padding: 26px 24px; margin-top: 12px;
        box-shadow: 0 12px 32px rgba(80, 64, 48, .10); }
h1 { font-size: 27px; letter-spacing: -0.02em; margin: 6px 0 4px; line-height: 1.25; }
.dek { color: #5c554e; font-size: 16px; margin: 0 0 6px; }
h2 { font-size: 19px; margin: 24px 0 6px; letter-spacing: -0.01em; }
p { margin: 8px 0; }
ul { margin: 8px 0; padding-left: 22px; }
li { margin: 4px 0; }
.pill { display: inline-block; background: #F4F1EA; border-radius: 999px; padding: 5px 12px;
        font-size: 12.5px; font-weight: 700; color: #6b6259; }
details.prods { margin-top: 22px; border: 1px solid #E7DECD; border-radius: 14px; overflow: hidden; }
details.prods summary { cursor: pointer; list-style: none; display: flex;
                        align-items: center; justify-content: space-between;
                        background: #FBF6EC; padding: 13px 15px; font-weight: 700; font-size: 15px; }
details.prods summary::-webkit-details-marker { display: none; }
.prod { padding: 13px 15px; border-top: 1px solid #EFE7D6; display: flex; gap: 12px; }
.prod img { width: 84px; height: 84px; object-fit: cover; border-radius: 10px; flex: none; }
.prod b { display: block; font-size: 14.5px; }
.prod .ppitch { display: block; font-size: 13.5px; color: #5c554e; margin: 3px 0 2px; }
a.pbtn { display: inline-block; margin-top: 8px; background: #4F6146; color: #fff; font-weight: 700;
         font-size: 14px; text-decoration: none; border-radius: 10px; padding: 9px 14px; }
.padv { display: block; font-size: 11.5px; color: #aaa093; margin-top: 6px; }
.advbox { margin-top: 20px; font-size: 12px; color: #a89e90; }
.mailbox { margin-top: 16px; border: 1px dashed #C9BFAE; border-radius: 14px; padding: 14px 15px;
           font-size: 14px; color: #6b6259; }
footer { text-align: center; font-size: 12.5px; color: #8a827a; margin-top: 26px; }
footer a { color: #6b6259; font-weight: 600; }
"""


def _parse(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    if text.startswith("---"):
        _, fm, text = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    return meta, text.strip()


def _inline(s: str) -> str:
    s = _html.escape(s)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def _render_md(text: str) -> str:
    out, in_list = [], False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h2>{_inline(s[3:])}</h2>")
        elif s.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(s[2:])}</li>")
        elif s:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{_inline(s)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _prodotti(nid: str, ids: list) -> str:
    cfg = yaml.safe_load((ROOT / "config" / "nicchie" / f"{nid}.yaml").read_text(encoding="utf-8"))
    by_id = {p.get("id"): p for p in cfg.get("prodotti", [])}
    cards = []
    for pid in ids or []:
        p = by_id.get(pid)
        link = ((p or {}).get("link") or "").strip()
        if not p or not link or "amazon." not in link:
            continue
        idee = [str(i).strip().rstrip(".") for i in (p.get("idee") or []) if str(i).strip()]
        pitch = f'<span class="ppitch">{_html.escape(idee[0])}.</span>' if idee else ""
        m = re.search(r"/dp/([A-Z0-9]{10})", link)
        thumb = (f'<img src="../prod/{m.group(1)}.jpg" alt="" loading="lazy">' if m else "")
        cards.append(
            f'<div class="prod">{thumb}<div><b>{_html.escape(p.get("titolo", pid))}</b>{pitch}'
            f'<a class="pbtn" href="{_html.escape(link)}">Vedi su Amazon →</a>'
            f'<span class="padv">link affiliato · #adv</span></div></div>'
        )
    if not cards:
        return ""
    return (f'<details class="prods"><summary><span>🛒 Prodotti citati · {len(cards)}</span>'
            f'<span>▾</span></summary>{"".join(cards)}</details>')


def genera() -> list[Path]:
    """Rende le guide PUBBLICABILI oggi; ritorna le pagine scritte.

    Scheduling: frontmatter opzionale `pubblica_dal: YYYY-MM-DD` — le guide
    future restano invisibili (niente pagina, niente indice, niente feed) finché
    non arriva la data. Così si accumulano code e l'RSS le rilascia col ritmo giusto.
    """
    from datetime import date

    DST.mkdir(parents=True, exist_ok=True)
    oggi = date.today().isoformat()
    fatte: list[Path] = []
    programmate = 0
    indice: list[tuple[str, str, str, str]] = []  # (nicchia, slug, titolo, board)
    for src in sorted(SRC.glob("*.md")):
        slug = src.stem  # = item id (casa-c01): URL stabili per sempre
        nid = NICCHIA_PER_PREFISSO.get(slug.split("-")[0], slug.split("-")[0])
        meta, body = _parse(src)
        dal = str(meta.get("pubblica_dal") or "")
        if dal and dal > oggi:
            programmate += 1
            continue
        titolo = meta.get("titolo", slug)
        descr = meta.get("descrizione", "")
        board = meta.get("board", "")
        prods = _prodotti(nid, meta.get("prodotti") or [])
        pagina = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(titolo)} — Quattro Mondi</title>
<meta name="description" content="{_html.escape(descr)}">
<meta name="theme-color" content="#F4F1EA">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<a class="crumb" href="../">← Quattro Mondi</a>
<div class="card">
<span class="pill">{_html.escape(board)}</span>
<h1>{_html.escape(titolo)}</h1>
<p class="dek">{_html.escape(descr)}</p>
{_render_md(body)}
{prods}
<div class="advbox">Questa pagina contiene link affiliati Amazon (#adv): se acquisti tramite questi link ricevo una commissione, senza costi extra per te.</div>
<div class="mailbox">📩 Vuoi la versione stampabile di questa guida? <i>Prossimamente: checklist PDF gratis via email.</i></div>
<!-- EMAIL: form Brevo/MailerLite qui quando attivo -->
</div>
<footer><a href="../">Quattro Mondi</a> · <a href="../privacy.html">Privacy</a></footer>
</div>
</body>
</html>
"""
        dst = DST / f"{slug}.html"
        dst.write_text(pagina, encoding="utf-8")
        fatte.append(dst)
        indice.append((nid, slug, titolo, board))
    # indice guide
    blocchi = []
    for nid in sorted({n for n, _, _, _ in indice}):
        items = "\n".join(
            f'<p><a href="./{s}.html">{_html.escape(t)}</a><br><span class="pill">{_html.escape(b)}</span></p>'
            for n, s, t, b in indice if n == nid
        )
        blocchi.append(f"<h2>{nid.capitalize()}</h2>\n{items}")
    (DST / "index.html").write_text(
        f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tutte le guide — Quattro Mondi</title>
<meta name="theme-color" content="#F4F1EA">
<!-- verifica Pinterest @contiinordine (claim .../pinn-site/guide/) -->
<meta name="p:domain_verify" content="100341cd2824c9ed1d36f6fc999d4a71"/>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<a class="crumb" href="../">← Quattro Mondi</a>
<div class="card">
<h1>📚 Tutte le guide</h1>
<p class="dek">Consigli pratici veri, uno per argomento. La lista cresce ogni settimana.</p>
{"".join(blocchi) if blocchi else "<p>Nessuna guida ancora. Torna presto.</p>"}
</div>
<footer><a href="../">Quattro Mondi</a> · <a href="../privacy.html">Privacy</a></footer>
</div>
</body>
</html>
""",
        encoding="utf-8",
    )
    print(f"guide: {len(fatte)} pagine + indice ({programmate} programmate per dopo)")
    return fatte


if __name__ == "__main__":
    genera()
