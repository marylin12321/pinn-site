#!/usr/bin/env python3
"""Genera la landing page unica (site/index.html) leggendo i 4 config di nicchia.

La pagina è il "centralino": un solo link da mettere sui 4 profili Pinterest,
con una sezione per mondo (colori delle palette, bottone al profilo) e spazi
già pronti per affiliati + email. Rilancialo ogni volta che cambi handle,
nomi o palette — la pagina resta sincronizzata ai config (fonte unica).

Uso:
  python3 tools/build_landing.py            # scrive site/index.html
  python3 tools/build_landing.py --check    # valida l'HTML generato (link e struttura)

Deploy: copia site/index.html nella root del repo Pages (lo fa in automatico
tools/pubblica_immagini.py a ogni giro) → https://<tu>.github.io/pinn-site/
"""
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

TAGLINE = {
    "casa": "Idee semplici per organizzare casa, piccoli spazi e pulizie senza stress.",
    "cibo": "Ricette sane e gustose, meal prep e dolci fatti in casa.",
    "finanza": "Budget, risparmi e debiti sotto controllo, un passo alla volta.",
    "parenting": "Idee gentle per bimbi, camerette e routine senza schermi.",
}
EMOJI = {"casa": "🏠", "cibo": "🍳", "finanza": "💰", "parenting": "🧸"}
CANONICHE = ["casa", "cibo", "finanza", "parenting"]


def _ordine_nicchie() -> list[str]:
    """Nicchie dai config (canoniche prima, eventuali nuove in coda): niente hardcode."""
    trovate = sorted(p.stem for p in (ROOT / "config" / "nicchie").glob("*.yaml"))
    return [n for n in CANONICHE if n in trovate] + [n for n in trovate if n not in CANONICHE]


ORDINE = _ordine_nicchie()
MONDI = {"casa": "Casa", "cibo": "Cucina", "finanza": "Soldi", "parenting": "Famiglia"}
TICK = "NUOVE IDEE OGNI SETTIMANA ✦ 100% GRATIS ✦ CASA · CUCINA · SOLDI · FAMIGLIA ✦ "
# Prezzi/rating indicativi per i prodotti con link (verificati live a sett. 2026;
# i prezzi Amazon cambiano: la pagina prodotto fa fede. Aggiornare ogni tanto).
EXTRA = {
  "casa-p01": ("≈36€", "4,6★"), "casa-p02": ("≈15€", "4,5★"),
  "casa-p03": ("27,99€", "4,4★"), "casa-p04": ("89,90€", "4,2★"),
  "casa-p05": ("da ≈20€", "4,6★"), "casa-p12": ("≈48€", "4,6★"),
  "cibo-p01": ("57,95€", "4,6★"), "cibo-p02": ("da ≈133€", "4,7★"),
  "cibo-p03": ("259,99€", "4,6★"), "cibo-p04": ("da ≈25€", "4,6★"),
  "cibo-p05": ("da ≈15€", "4,7★"),
  "fin-p07": ("≈12€", "4,5★"), "fin-p08": ("15,99€", "4,4★"),
  "par-p01": ("≈129€", "4,1★"), "par-p03": ("9,99€", "4,3★"),
  "par-p04": ("≈82€", "4,0★"), "par-p05": ("da ≈14€", "4,5★"),
  # Seconda ondata (rating da ricerca sett. 2026, prezzi omessi: cambiano spesso,
  # la pagina prodotto fa fede — le card mostrano solo ★).
  "casa-p13": ("", "4,1★"), "casa-p14": ("", "4,6★"),
  "casa-p15": ("", "4,3★"), "casa-p16": ("", "4,6★"),
  "casa-p17": ("", "4,3★"), "casa-p18": ("", "4,6★"),
  "casa-p19": ("", "4,6★"), "casa-p20": ("", "4,6★"),
  "cibo-p13": ("", "4,3★"), "cibo-p14": ("", "4,6★"),
  "cibo-p15": ("", "4,7★"), "cibo-p16": ("", "4,5★"),
  "cibo-p17": ("", "4,3★"), "cibo-p18": ("", "4,6★"),
  "cibo-p19": ("", "4,7★"), "cibo-p20": ("", "4,4★"),
  "fin-p13": ("", "4,5★"), "fin-p14": ("", "4,5★"),
  "fin-p15": ("", "4,6★"), "fin-p16": ("", "4,6★"),
  "fin-p17": ("", "4,7★"), "fin-p18": ("", "4,2★"),
  "fin-p19": ("", "4,7★"), "fin-p20": ("", "4,1★"),
  "par-p13": ("", "4,5★"), "par-p14": ("", "4,7★"),
  "par-p15": ("", "4,6★"), "par-p16": ("", "4,6★"),
  "par-p17": ("", "4,5★"), "par-p18": ("", "4,7★"),
  "par-p19": ("", "4,6★"), "par-p20": ("", "4,6★"),
}
SITE_URL = "https://marylin12321.github.io/pinn-site/"
# Bottoni/cover scuri per contrasto AAA col bianco (gli accenti chiari restano decorativi).
BTN = {"casa": "#4F6146", "cibo": "#9A5B0F", "finanza": "#12263F", "parenting": "#8E5A54"}

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
       Helvetica, Arial, sans-serif; color: #2E2A26; line-height: 1.55;
       background-color: #F4F1EA;
       background-image: radial-gradient(640px 320px at 8% -40px, #EDDFC9 0%, transparent 60%),
                         radial-gradient(560px 300px at 105% 240px, #E6D8CB 0%, transparent 60%); }
body::after { content: ""; position: fixed; inset: 0; pointer-events: none; opacity: .05;
       background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/><feColorMatrix type='saturate' values='0'/></filter><rect width='120' height='120' filter='url(%23n)' opacity='0.55'/></svg>"); }
.wrap { max-width: 600px; margin: 0 auto; padding: 34px 18px 52px; }
header { text-align: center; margin-bottom: 6px; }
.avatar { width: 92px; height: 92px; margin: 0 auto; border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          font-size: 30px; font-weight: 800; letter-spacing: 1px; color: #fff;
          border: 5px solid transparent;
          background: linear-gradient(#2E2A26, #2E2A26) padding-box,
                      conic-gradient(from 40deg, #7A8B6F, #E08A2E, #C9962B, #D89A94, #7A8B6F) border-box;
          box-shadow: 0 0 0 4px #fff, 0 12px 26px rgba(80, 64, 48, .22);
          animation: glow 3.2s ease-in-out infinite; }
@keyframes glow { 50% { box-shadow: 0 0 0 4px #fff, 0 0 36px rgba(224, 138, 46, .5); } }
header h1 { font-size: 32px; margin: 14px 0 2px; letter-spacing: -0.02em; }
header .sub { margin: 0; color: #5c554e; font-size: 16px; }
.pill { display: inline-block; margin-top: 12px; background: #fff;
        border: 1px solid #E2D9C9; border-radius: 999px; padding: 7px 15px;
        font-size: 13.5px; font-weight: 600; color: #6b6259; }
.stats { display: flex; gap: 10px; margin: 18px 0 4px; }
.stats div { flex: 1; background: #fff; border-radius: 14px; padding: 10px 6px;
             box-shadow: 0 4px 14px rgba(80, 64, 48, .07); }
.stats b { display: block; font-size: 20px; letter-spacing: -0.02em; }
.stats span { font-size: 12px; color: #8a827a; font-weight: 600; }
.tick { overflow: hidden; background: #2E2A26; color: #F4F1EA; border-radius: 12px;
        font-size: 12.5px; font-weight: 800; letter-spacing: .14em; padding: 11px 0;
        margin: 18px 0 24px; }
.tick-in { display: inline-block; white-space: nowrap; animation: tick 24s linear infinite; }
@keyframes tick { to { transform: translateX(-50%); } }
nav.chips { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center;
            margin: 0 0 24px; }
nav.chips a { text-decoration: none; font-size: 14px; font-weight: 600; color: #2E2A26;
              background: #fff; border: 1px solid #E0D6C4; border-radius: 999px;
              padding: 9px 15px; box-shadow: 0 2px 8px rgba(80, 64, 48, .06); }
section.mondo { background: #fff; border-radius: 22px; overflow: hidden;
                margin: 0 0 20px; box-shadow: 0 12px 32px rgba(80, 64, 48, .10);
                scroll-margin-top: 14px; }
.mondo .cover { position: relative; overflow: hidden; color: #fff;
                background: linear-gradient(105deg, var(--btn) 0%, var(--btn) 55%, transparent 100%),
                            var(--foto, none) center/cover, var(--btn);
                padding: 20px 20px 18px; display: flex; gap: 13px; align-items: center; }
.mondo .ghost { position: absolute; right: 10px; top: 50%; transform: translateY(-54%);
                font-size: 66px; font-weight: 800; letter-spacing: -0.04em;
                color: rgba(255, 255, 255, .16); }
.cico { flex: none; width: 54px; height: 54px; border-radius: 16px;
        background: rgba(255, 255, 255, .16);
        display: flex; align-items: center; justify-content: center; font-size: 29px; }
.mondo .num { font-size: 12px; font-weight: 800; letter-spacing: .2em;
              color: rgba(255, 255, 255, .8); }
section.mondo h2 { margin: 2px 0 0; font-size: 22px; letter-spacing: -0.02em;
                   text-shadow: 0 2px 12px rgba(0, 0, 0, .25); }
.mondo .body { padding: 18px 20px; }
section.mondo .tag { margin: 0; color: #5c554e; font-size: 15px; }
section.mondo .boards { display: flex; flex-wrap: wrap; gap: 6px; margin: 13px 0 15px; }
section.mondo .boards span { font-size: 12.5px; background: var(--sf); color: var(--tx);
                             border-radius: 999px; padding: 5px 11px; font-weight: 600; }
a.btn { display: flex; align-items: center; justify-content: space-between; gap: 10px;
        background: var(--btn); color: #fff; text-decoration: none;
        border-radius: 14px; padding: 13px 16px;
        box-shadow: 0 8px 18px rgba(0, 0, 0, .16); }
a.btn .bl b { display: block; font-size: 16.5px; }
a.btn .bl i { display: block; font-style: normal; font-size: 13px; opacity: .78; }
a.btn .arr { font-size: 24px; transition: transform .15s; }
a.btn:active { transform: scale(0.99); }
a.btn:active .arr { transform: translateX(5px); }
.soon { margin: 13px 0 0; font-size: 13.5px; color: #8a827a; text-align: center; }
details.prods { margin-top: 15px; border: 1px solid #E7DECD; border-radius: 14px; overflow: hidden; }
details.prods summary { cursor: pointer; list-style: none; display: flex;
                        align-items: center; justify-content: space-between;
                        background: var(--sf); padding: 13px 15px;
                        font-weight: 700; font-size: 15px; }
details.prods summary::-webkit-details-marker { display: none; }
details.prods summary .chev { transition: transform .2s; color: var(--btn); font-size: 18px; }
details.prods[open] summary .chev { transform: rotate(180deg); }
.prod { padding: 13px 15px; border-top: 1px solid #EFE7D6; display: flex; gap: 12px; }
.prod img { width: 84px; height: 84px; object-fit: cover; border-radius: 10px; flex: none; }
.prod b { display: block; font-size: 14.5px; }
.prod .pmeta { display: block; font-size: 13px; color: #8a827a; margin: 2px 0 9px; }
a.pbtn { display: inline-block; background: var(--btn); color: #fff; font-weight: 700;
         font-size: 14px; text-decoration: none; border-radius: 10px; padding: 9px 14px; }
.prod .padv { display: block; font-size: 10.5px; color: #b5ab9c; margin-top: 5px; }
footer { background: #2E2A26; color: #CDC5B9; border-radius: 18px; padding: 18px;
         text-align: center; font-size: 12.5px; margin-top: 26px; }
footer nav a { color: #F4F1EA; text-decoration: none; font-weight: 600; margin: 0 7px; }
@media (hover: hover) {
  .mondo { transition: transform .2s; }
  .mondo:hover { transform: translateY(-2px); }
  a.btn:hover .arr { transform: translateX(5px); }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  .tick-in, .avatar { animation: none; }
}
"""


def _prodotti_html(cfg: dict) -> str:
    """Card PRODOTTI CONSIGLIATI dai link affiliati del config (con #adv in chiaro)."""
    cards = []
    for p in cfg.get("prodotti", []):
        link = (p.get("link") or "").strip()
        if not link or "amazon." not in link:
            continue
        prezzo, rating = EXTRA.get(p.get("id", ""), ("", ""))
        meta = " · ".join(x for x in (rating, prezzo) if x)
        m = re.search(r"/dp/([A-Z0-9]{10})", link)
        thumb = (f'<img src="prod/{m.group(1)}.jpg" alt="" loading="lazy">' if m else "")
        cards.append(
            f'<div class="prod">{thumb}<div><b>{p.get("titolo", p.get("id", ""))}</b>'
            f'<span class="pmeta">{meta}</span></div>'
            f'<a class="pbtn" href="{link}">Vedi su Amazon →</a>'
            f'<span class="padv">link affiliato · #adv</span></div>'
        )
    if not cards:
        return ""
    return (f'<details class="prods"><summary><span>🎁 Prodotti consigliati · {len(cards)}</span>'
            f'<span class="chev">▾</span></summary>{"".join(cards)}</details>'
            f'<!-- AFFILIATI: blocco generato dai link del config -->')


def _sezione(nid: str, cfg: dict) -> str:
    nicchia = cfg.get("nicchia", {})
    design = cfg.get("design", {}) or {}
    pal = design.get("palette", {}) or {}
    handle = (nicchia.get("handle") or "").strip().lstrip("@")
    nome = nicchia.get("nome", nid)
    boards = nicchia.get("boards") or []
    chips = "".join(f"<span>{b}</span>" for b in boards)
    num = f"{ORDINE.index(nid) + 1:02d}"
    prods = _prodotti_html(cfg)
    coda = prods if prods else f'<p class="soon">🔜 Qui arriveranno i prodotti consigliati del mondo {nome}.</p>'
    return f"""<section class="mondo" id="{nid}" style="--acc:{pal.get('accento', '#555')};
      --btn:{BTN.get(nid, '#333')}; --sf:{pal.get('sfondo', '#fff')}; --tx:{pal.get('testo', '#222')}">
  <div class="cover" style="--foto:url('covers/{nid}.jpg')">
    <span class="cico">{EMOJI.get(nid, '•')}</span>
    <div><div class="num">{num} · MONDO {MONDI.get(nid, nid).upper()}</div><h2>{nome}</h2></div>
    <span class="ghost">{num}</span>
  </div>
  <div class="body">
  <p class="tag">{TAGLINE.get(nid, '')}</p>
  <div class="boards">{chips}</div>
  <a class="btn" href="https://pinterest.com/{handle}/"><span class="bl"><b>Vai al profilo Pinterest</b><i>@{handle}</i></span><span class="arr">→</span></a>
  {coda}
  </div>
  <!-- EMAIL-{nid.upper()}: incolla qui il form MailerLite/Brevo quando hai la landing -->
</section>"""


def genera() -> Path:
    cfgs = {}
    for nid in ORDINE:
        p = ROOT / "config" / "nicchie" / f"{nid}.yaml"
        cfgs[nid] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    chips = "".join(
        f'<a href="#{nid}">{EMOJI.get(nid, "")} {cfgs[nid].get("nicchia", {}).get("nome", nid)}</a>'
        for nid in ORDINE
    )
    sezioni = "\n".join(_sezione(nid, cfgs[nid]) for nid in ORDINE)
    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quattro Mondi — Idee per Casa, Cucina, Soldi e Famiglia</title>
<meta name="description" content="Un solo punto di partenza per quattro mondi:
  organizzazione casa, ricette sane, budget sotto controllo e idee per bimbi.">
<!-- CLAIM-PINTEREST: incolla qui il meta tag di verifica del sito quando lo claimi -->
<!-- verifica Pinterest @coloridigusto (claim .../pinn-site/) -->
<meta name="p:domain_verify" content="19bfe0ef32d0904b71c9810c2ef953e1"/>
<meta name="theme-color" content="#F4F1EA">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%232E2A26'/%3E%3Ctext x='32' y='43' font-size='30' text-anchor='middle' fill='white' font-family='Arial' font-weight='bold'%3EQ%3C/text%3E%3C/svg%3E">
<meta property="og:type" content="website">
<meta property="og:title" content="Quattro Mondi — Idee per Casa, Cucina, Soldi e Famiglia">
<meta property="og:description" content="Un solo punto di partenza per quattro mondi: organizzazione casa, ricette sane, budget sotto controllo e idee per bimbi.">
<meta property="og:url" content="https://marylin12321.github.io/pinn-site/">
<meta property="og:image" content="https://marylin12321.github.io/pinn-site/covers/cibo.jpg">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="avatar">QM</div>
  <h1>Quattro Mondi</h1>
  <p class="sub">Idee per Casa, Cucina, Soldi e Famiglia.</p>
  <span class="pill">✨ Nuove idee ogni settimana · gratis</span><br>
  <a class="pill" style="text-decoration:none;margin-top:8px" href="./guide/">📚 Tutte le guide →</a>
  <div class="stats">
    <div><b>4</b><span>mondi</span></div>
    <div><b>20</b><span>board</span></div>
    <div><b>100%</b><span>gratis</span></div>
  </div>
</header>
<div class="tick"><div class="tick-in">{TICK}{TICK}</div></div>
<nav class="chips">{chips}</nav>
{sezioni}
<footer>
  <nav><a href="#">↑ Torna su</a> · <a href="#casa">Casa</a> · <a href="#cibo">Cucina</a> · <a href="#finanza">Soldi</a> · <a href="#parenting">Famiglia</a> · <a href="./privacy.html">Privacy</a></nav>
  <p>Trasparenza: se un giorno troverai link affiliati, saranno sempre segnalati come #adv.</p>
</footer>
</div>
</body>
</html>
"""
    SITE.mkdir(parents=True, exist_ok=True)
    dst = SITE / "index.html"
    dst.write_text(html, encoding="utf-8")
    print(f"landing scritta: {dst.relative_to(ROOT)} ({len(html)} byte)")
    return dst


class _Check(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.sezioni: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self.links.append(d["href"])
        if tag == "section" and d.get("id"):
            self.sezioni.append(d["id"])


def valida(p: Path) -> bool:
    c = _Check()
    c.feed(p.read_text(encoding="utf-8"))
    ok = True
    if c.sezioni != ORDINE:
        print(f"CHECK ✗ sezioni: {c.sezioni} (attese {ORDINE})")
        ok = False
    profili = [l for l in c.links if l.startswith("https://pinterest.com/")]
    if len(profili) != 4 or any(l.rstrip("/").endswith("pinterest.com") for l in profili):
        print(f"CHECK ✗ link profili: {profili}")
        ok = False
    if ok:
        print(f"CHECK ✓ 4 sezioni, 4 link profilo: {profili}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="valida l'HTML dopo averlo generato")
    args = ap.parse_args()
    dst = genera()
    if args.check and not valida(dst):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
