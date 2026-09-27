#!/usr/bin/env python3
"""Stampa di printables finanziari: layout A4 vettoriale via Chrome headless.

Ogni printable è definito in config/printable.yaml (titolo, descrizione,
dati, board, guida collegata, prodotti Amazon). Questo modulo:
  1. renderizza l'HTML/A4 del printable (template interno)
  2. chiama google-chrome --headless → site/printable/<slug>.pdf  (vettoriale)
  3. pdftoppm → site/printable/<slug>_preview.png  (anteprima per il sito)
  4. PIL  → covers/printable-<slug>.jpg  (cover pin 1000×1500)

Uso:
  python3 tools/build_printable.py                     # tutti i printable
  python3 tools/build_printable.py --slug budget-mensile # uno solo
  python3 tools/build_printable.py --no-cover            # senza cover pin

Le anteprime e le cover entrano nella build del sito (build_sito.py).
"""
from __future__ import annotations

import hashlib, os, shutil, subprocess, sys, tempfile
from pathlib import Path

import build_guide  # noqa: E402 — CSS inline delle pagine sito
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import url_base  # noqa: E402 — radice del sito, fonte unica

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "guide"
SITE = ROOT / "site"
COV = SITE / "covers"
PRI = SITE / "printable"
YAML_PATH = ROOT / "config" / "printable.yaml"


def _carica() -> list[dict]:
    import yaml
    return [d for d in yaml.safe_load_all(YAML_PATH.read_text(encoding="utf-8")) if d] or []


def _font() -> str:
    for f in ("Poppins-Regular.ttf", "Lato-Regular.ttf"):
        p = ROOT / "assets" / "fonts" / f
        if p.exists():
            return str(p)
    return ""


# ---------------------------------------------------------------- template
def _css() -> str:
    f = _font()
    body_font = f'font-family: "{Path(f).stem}", sans-serif;' if f else ""
    return f"""
@page {{ size: A4; margin: 12mm 13mm 14mm 13mm; }}
* {{ box-sizing: border-box; }}
body {{ {body_font} color:#12263F; font-size:9.2pt; margin:0; line-height:1.35; }}
h1 {{ color:#1E7A5F; font-size:17pt; margin:0 0 2mm 0; }}
h2 {{ color:#0E4C76; font-size:11pt; margin:3mm 0 1.5mm 0; border-bottom:1.5pt solid #1E7A5F; padding-bottom:1mm; }}
h3 {{ color:#C9962B; font-size:9.6pt; margin:2mm 0 1mm 0; }}
p  {{ margin:0 0 1.5mm 0; }}
.sottotitolo {{ color:#5A6B7B; font-size:8.4pt; margin:0 0 3mm 0; }}
.tabella {{ width:100%; border-collapse:collapse; margin:1.5mm 0 2mm 0; }}
.tabella th {{ background:#1E7A5F; color:#fff; padding:1.4mm; text-align:left; font-size:8.4pt; }}
.tabella td {{ border:0.6pt solid #C8D2DC; padding:1.2mm; font-size:8.4pt; }}
.tabella td.num {{ text-align:right; }}
.tabella tr:nth-child(even) td {{ background:#F7F9FB; }}
.riga {{ display:flex; gap:2mm; margin-bottom:1.2mm; }}
.riga > div {{ flex:1; }}
.input {{ border-bottom:0.8pt solid #12263F; padding:0.8mm 0; width:100%; }}
.area {{ border:0.8pt dashed #C8D2DC; padding:1.5mm; min-height:8mm; }}
.blocco {{ border:1pt solid #0E4C76; border-radius:4pt; padding:2mm; margin-bottom:2.5mm; }}
.blocco h3 {{ margin-top:0; }}
.intestazione {{ display:flex; justify-content:space-between; align-items:flex-end; border-bottom:2pt solid #1E7A5F; padding-bottom:1.5mm; margin-bottom:3mm; }}
.badge {{ background:#C9962B; color:#fff; font-size:7.6pt; padding:0.8mm 2mm; border-radius:2mm; }}
.foot {{ margin-top:4mm; border-top:0.8pt solid #C8D2DC; padding-top:1.5mm; font-size:7.6pt; color:#5A6B7B; }}
"""


def _html(titolo: str, sottotitolo: str, corpo: str) -> str:
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>{titolo}</title><style>{_css()}</style></head><body>
<div class="intestazione"><h1>{titolo}</h1><span class="badge">PDF GRATIS</span></div>
<div class="sottotitolo">{sottotitolo}</div>
{corpo}
<div class="foot">© TuttoInOrdine · guida correlata: <a href="{{GUIDA}}">{{GUIDAT}}</a></div>
</body></html>"""


def _tpl_budget(data: dict) -> str:
    redditi = "".join(f'<tr><td>{n}</td><td class="num">{v}</td></tr>' for n, v in data.get("redditi", []))
    return _html(data["titolo"], data["sottotitolo"], f"""
<h2>Entrate del mese</h2>
<table class="tabella"><tr><th>Fonte</th><th style="text-align:right">Importo €</th></tr>{redditi}
<tr><td><b>TOTALE ENTRATE</b></td><td class="num"><b>{data.get("totale_redditi","")}</b></td></tr></table>
<div class="blocco"><h3>50% → Bisogni (essenziali)</h3>
<div class="riga">{"".join(f'<div><span>{n}</span><div class="input"></div></div>' for n in data.get("bisogni", []))}</div></div>
<div class="blocco"><h3>30% → Desideri (facoltativi)</h3>
<div class="riga">{"".join(f'<div><span>{n}</span><div class="input"></div></div>' for n in data.get("desideri", []))}</div></div>
<div class="blocco"><h3>20% → Risparmio e debiti</h3>
<div class="riga">{"".join(f'<div><span>{n}</span><div class="input"></div></div>' for n in data.get("risparmio", []))}</div></div>
<h2>Spese fisse mensili</h2>
<table class="tabella"><tr><th>Voce</th><th style="text-align:right">Importo €</th><th>Payday</th></tr>
{data.get("fisse","")}</table>
<h2>Note</h2><div class="area"></div>""")


def _tpl_tracker(data: dict) -> str:
    colonne = "".join(f"<th>{c}</th>" for c in data.get("colonne", []))
    righe = "".join(
        "<tr>" + "".join(f'<td><div class="input"></div></td>' for _ in data.get("colonne", [])) + "</tr>"
        for _ in range(data.get("giorni", 31)))
    return _html(data["titolo"], data["sottotitolo"], f"""
<h2>Traccia ogni uscita</h2>
<table class="tabella"><tr><th>Giorno</th>{colonne}</tr>{righe}</table>
<h2>Totale settimanale</h2>
<table class="tabella"><tr><th>Settimana</th><th style="text-align:right">Speso €</th><th style="text-align:right">Budget €</th><th style="text-align:right">Differenza</th></tr>
{data.get("settimanali","")}</table>
<h2>Da pagare questa settimana</h2><div class="area"></div>""")


def _tpl_debiti(data: dict) -> str:
    creditori = "".join(
        f'<tr><td>{c["nome"]}</td><td class="num">{c["saldo"]}</td><td class="num">{c["minimo"]}</td>'
        f'<td class="num">{c.get("percentuale","")}</td><td class="num"></td></tr>'
        for c in data.get("creditori", []))
    return _html(data["titolo"], data["sottotitolo"], f"""
<h2>Elenco debiti</h2>
<table class="tabella"><tr><th>Creditore</th><th style="text-align:right">Saldo €</th><th style="text-align:right">Rata minima</th><th style="text-align:right">% del debito</th><th style="text-align:right">Data pagato</th></tr>
{creditori}</table>
<h2>Strategia: {data.get("strategia","")}</h2>
<p>{data.get("spiegazione","")}</p>
<h2>Payment tracker mensile</h2>
<table class="tabella"><tr><th>Mese</th><th style="text-align:right">Totale pagato €</th><th style="text-align:right">Debito residuo €</th></tr>
{data.get("mesi","")}</table>""")


def _tpl_sfida(data: dict) -> str:
    caselle = "".join(f'<td><div class="input"></div></td>' for _ in range(52))
    return _html(data["titolo"], data["sottotitolo"], f"""
<h2>Sfida 52 settimane</h2>
<p>Ogni settimana versi quanto indicato. Completa la casella quando hai versato.</p>
<table class="tabella"><tr>{caselle}</tr></table>
<h2>Totale accumulato</h2>
<table class="tabella"><tr><th>Mese</th><th style="text-align:right">Versato €</th><th style="text-align:right">Totale €</th></tr>
{data.get("mesi","")}</table>
<h2>Obiettivo finale</h2><div class="area"></div>""")


def _tpl_calcolatore(data: dict) -> str:
    obiettivo = data.get("obiettivo", "10.000 €")
    mesi = "".join(
        f'<tr><td>{m}</td><td class="num"><div class="input"></div></td>'
        f'<td class="num"></td><td class="num"></td></tr>'
        for m in data.get("mesi_lista", ["Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"]))
    return _html(data["titolo"], data["sottotitolo"], f"""
<h2>Obiettivo: {obiettivo}</h2>
<div class="blocco"><p>Versa ogni mese fino a raggiungere l'obiettivo. Traccia il progresso.</p></div>
<h2>Tracker mensile</h2>
<table class="tabella"><tr><th>Mese</th><th style="text-align:right">Versato €</th><th style="text-align:right">Totale €</th><th style="text-align:right">%</th></tr>
{mesi}</table>
<h2>Da dove arriva il denaro?</h2>
<div class="area"></div>""")


def _tpl_buste(data: dict) -> str:
    etichette = "".join(
        f'<div class="riga"><div><b>{n}</b></div><div class="input"></div>'
        f'<div class="input"></div></div>'
        for n in data.get("etichette", ["Affitto","Bollette","Spesa","Risparmio","Libero","Altro"]))
    return _html(data["titolo"], data["sottotitolo"], f"""
<h2>Cash stuffing: 6 buste</h2>
<p>Stampa, ritaglia, scrivi l'importo. Metti i contanti in ogni busta e usa solo quella.</p>
{etichette}
<h2>Riepilogo mensile</h2>
<table class="tabella"><tr><th>Busta</th><th style="text-align:right">Assegnato €</th><th style="text-align:right">Speso €</th></tr>
{data.get("riepilogo","")}</table>""")


def _tpl_agenda(data: dict) -> str:
    giorni = "".join(
        f'<tr><td>{d}</td><td class="num"><div class="input"></div></td>'
        f'<td class="num"><div class="input"></div></td><td class="num"></td></tr>'
        for d in data.get("giorni_lista", ["Lun","Mar","Mer","Gio","Ven","Sab","Dom"]))
    return _html(data["titolo"], data["sottotitolo"], f"""
<h2>Agenda finanziaria mensile</h2>
<p>Una riga per ogni giorno: entra, esce, saldo. Scrivi qui sotto.</p>
<table class="tabella"><tr><th>Giorno</th><th style="text-align:right">Entrata €</th><th style="text-align:right">Uscita €</th><th style="text-align:right">Saldo</th></tr>
{giorni}</table>
<h2>Note</h2><div class="area"></div>""")


_TEMPLATES = {"budget_mensile": _tpl_budget, "tracker_spese": _tpl_tracker,
              "piano_debiti": _tpl_debiti, "sfida_52_settimane": _tpl_sfida,
              "calcolatore_obiettivo": _tpl_calcolatore,
              "cash_stuffing_buste": _tpl_buste,
              "agenda_finanziaria": _tpl_agenda}


# ---------------------------------------------------------------- build
def _render(spec: dict) -> str:
    fn = _TEMPLATES.get(spec["template"])
    if not fn:
        raise ValueError(f"template sconosciuto: {spec['template']}")
    data = dict(spec["dati"])
    data.setdefault("titolo", spec["titolo"])
    data.setdefault("sottotitolo", spec["sottotitolo"])
    corpo = fn(data)
    return _html(spec["titolo"], spec["sottotitolo"], corpo.replace("{{GUIDA}}", spec.get("guida_url","")).replace("{{GUIDAT}}", spec.get("guida_titolo","")))


def build(spec: dict, force: bool = False) -> dict | None:
    slug = spec["slug"]
    pdf = PRI / f"{slug}.pdf"
    png = PRI / f"{slug}_preview.png"
    PRI.mkdir(parents=True, exist_ok=True)
    if not force and pdf.exists() and png.exists():
        return None
    html = _render(spec)
    tmp = tempfile.mkdtemp(prefix="print-")
    try:
        h = Path(tmp) / "page.html"
        h.write_text(html, encoding="utf-8")
        subprocess.run(["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
                        "--user-data-dir=/tmp/opencode/chrome-prof", "--no-pdf-header-footer",
                        "--print-to-pdf=" + str(pdf), "--print-to-pdf-no-header", "--print-to-pdf-no-footer",
                        "--no-pdf-header-footer", f"file://{h}"],
                       check=True, capture_output=True, timeout=120)
        subprocess.run(["pdftoppm", "-r", "96", "-png", "-f", "1", "-l", "1", str(pdf), str(Path(tmp) / "prev")],
                       check=True, capture_output=True, timeout=60)
        src = next(p for p in Path(tmp).glob("prev*.png"))
        shutil.move(str(src), str(png))
        return {"slug": slug, "pdf": str(pdf), "png": str(png)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cover(spec: dict, src_preview: str | None = None) -> str | None:
    """Genera covers/printable-<slug>.jpg (mockup printable 1000×1500)."""
    if src_preview is None:
        src_preview = str(PRI / f"{spec['slug']}_preview.png")
    if not Path(src_preview).exists():
        return None
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1000, 1500
    bg = Image.new("RGB", (W, H), spec.get("colore", "#F7F9FB"))
    # area contenuto con ombra
    prev = Image.open(src_preview).convert("RGB")
    prev.thumbnail((760, 1070))
    pad = 3
    shadow = Image.new("RGBA", (prev.width + pad*2, prev.height + pad*2), (0,0,0,0))
    shadow.paste((0,0,0,60), (0,0) + shadow.size)
    shadow.paste(prev, (pad, pad))
    x = (W - shadow.width) // 2
    y = 30
    bg.paste(shadow, (x, y), shadow)
    # badge
    draw = ImageDraw.Draw(bg)
    fnt = ImageFont.truetype(str(ROOT/"assets"/"fonts"/"Poppins-Bold.ttf"), 26)
    draw.rounded_rectangle([x, y-60, x+shadow.width, y-60+44], fill="#C9962B", radius=8)
    draw.text((x+16, y-60+12), "PDF GRATIS", fill="#fff", font=fnt)
    # titolo
    f2 = ImageFont.truetype(str(ROOT/"assets"/"fonts"/"Poppins-Bold.ttf"), 22)
    draw.text((x, y+shadow.height+16), spec["titolo"][:44], fill="#12263F", font=f2)
    out = COV / f"printable-{spec['slug']}.jpg"
    bg.save(out, "JPEG", quality=88)
    return str(out)


def _site_base() -> str:
    return url_base.site_base(ROOT)


def _pagina(spec: dict, preview_png: str) -> None:
    """Scrive site/printable/<slug>.html (landing con anteprima + download)."""
    base = _site_base()
    pdf_url = f"{base}printable/{spec['slug']}.pdf"
    guida_url = spec.get("guida_url") or f"{base}guide/{spec.get('guida','')}.html"
    prodotti = ""
    for p in spec.get("prodotti", []):
        link = p.get("link", "")
        prodotti += (
            f'<div class="prod"><img src="{base}covers/{p["id"]}.jpg" alt="{p["id"]}" '
            f'loading="lazy"><div><b>{p.get("note","")}</b>'
            f'<span class="ppitch">{p.get("titolo","")}</span>'
            f'<a class="pbtn" href="{link}">Vai su Amazon</a>'
            f'<span class="padv">#adv</span></div></div>')
    html = f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>{spec['titolo']} — stampabile gratis</title>
<meta name="description" content="{spec['sottotitolo']}">
<style>{build_guide.CSS}</style></head><body>
<div class="wrap">
<a class="crumb" href="{base}">← TuttoInOrdine</a>
<div class="card">
<h1>{spec['titolo']}</h1>
<p class="dek">{spec['sottotitolo']}</p>
<img src="{preview_png}" alt="{spec['titolo']}" style="width:100%;border-radius:14px;margin:14px 0">
<a class="pbtn" href="{pdf_url}" download="">Scarica il PDF gratis (A4)</a>
<div class="advbox">{spec.get('descrizione','')}</div>
<h2>Nel PDF</h2><ul>{''.join(f'<li>{b}</li>' for b in spec.get('contiene',[]))}</ul>
<h2>Guida correlata</h2><p><a href="{guida_url}">{spec.get('guida_titolo','')}</a></p>
<h2>Strumenti correlati</h2>
<details class="prods"><summary>Prodotti Amazon ({len(spec.get('prodotti',[]))}) ▾</summary>{prodotti}</details>
<footer><a href="{base}">TuttoInOrdine</a> · <a href="{guida_url}">guida</a></footer>
</div></div></body></html>"""
    dst = SITE / "printable" / f"{spec['slug']}.html"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(html, encoding="utf-8")


def genera() -> list[dict]:
    """Build di TUTTI i printable: PDF + preview + cover + pagina sito.

    Il PDF e la preview sono gli unici artefatti che richiedono i tool di
    sistema (google-chrome + pdftoppm): si generano solo se mancano, altrimenti
    vengono riutilizzati. Cover e pagina invece si rigenerano sempre: dipendono
    solo dalla preview e dal testo in config, e servono a tenere allineati i
    copy senza dover ricostruire i PDF.

    Questo è ciò che permette alla pipeline GitHub di ricostruire il sito senza
    tool di sistema: in CI i printable esistenti vengono copiati nell'albero di
    build e quindi risultano già pronti.
    """
    specs = _carica()
    for spec in specs:
        r = build(spec)
        png = Path(r["png"]) if r else PRI / f"{spec['slug']}_preview.png"
        if not png.exists():
            print(f"  {spec['slug']}: nessuna preview, salto")
            continue
        c = cover(spec, str(png))
        _pagina(spec, str(png))
        stato = f"{Path(r['pdf']).name} · preview" if r else "pdf riutilizzato"
        print(f"  ✓ {spec['slug']}: {stato} · cover={'✓' if c else '—'} · pagina ✓")
    print(f"printable generati: {len(specs)}")
    return specs


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--no-cover", action="store_true")
    args = ap.parse_args()
    specs = _carica()
    if args.slug:
        specs = [s for s in specs if s["slug"] == args.slug]
    ok = 0
    for spec in specs:
        r = build(spec)
        if not r:
            print(f"  {spec['slug']}: già pronto")
            continue
        c = None if args.no_cover else cover(spec, r["png"])
        print(f"  ✓ {spec['slug']}: {r['pdf'].name} · preview · cover={'✓' if c else '—'}")
        ok += 1
    print(f"\nprintable generati: {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
