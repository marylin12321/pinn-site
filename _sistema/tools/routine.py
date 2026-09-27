#!/usr/bin/env python3
"""Routine giornaliera: un comando solo, pensata anche per cron.

  python3 tools/routine.py              # verifica → build → pubblica → controlli
  python3 tools/routine.py --no-push    # tutto tranne il push (prova)
  python3 tools/routine.py --link       # + salute dei 49 link Amazon (lento, ~1 min)

Cosa fa, in ordine:
  1. verifica config (blocca tutto se BLOCCANTE in modalità reale)
  2. cover guide (immagini uniche per ogni guida → pin RSS non deduplicati)
  3. build_sito --check (landing + guide pubblicabili oggi + feed + sitemap)
  4. pubblica_immagini (commit + push)
  5. controlli live (landing, sitemap, un feed per nicchia)
  6. coda guide: quante programmate restano e quando si esauriscono
  --link aggiunge il controllo di tutti i link Amazon (products KO = soldi persi)

Exit code: 0 tutto ok · 1 bloccante/errore (cron notifica).
Log: stdout (ridirigi su file in cron).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "guide"
TOKEN_FILE = Path.home() / ".github-token-pinn"


def _run(cmd: list[str], env_extra: dict | None = None) -> int:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    r = subprocess.run([sys.executable, *cmd], cwd=ROOT, env=env)
    return r.returncode


def _git_env() -> dict:
    """Auth git dal file token (così cron funziona senza env preparato)."""
    import base64

    raw = TOKEN_FILE.read_text().strip()
    b64 = base64.b64encode(f"x-access-token:{raw}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {b64}",
    }


def _check_url(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _coda_guide() -> tuple[int, str]:
    """Guide future programmate (pubblica_dal > oggi): quante e fino a quando."""
    oggi = date.today().isoformat()
    future = []
    for src in sorted(SRC.glob("*.md")):
        text = src.read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else {}
        dal = str((meta or {}).get("pubblica_dal") or "")
        if dal and dal > oggi:
            future.append(dal)
    if not future:
        return 0, "nessuna"
    return len(future), max(future)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--link", action="store_true",
                    help="controlla anche tutti i link Amazon (lento)")
    args = ap.parse_args()

    print("== 1/6 verifica ==")
    if _run(["src/main.py", "verifica"]) != 0:
        print("BLOCCANTE in verifica: routine fermata prima di pubblicare.")
        return 1

    print("== 2/6 cover guide ==")
    if _run(["tools/build_cover_guide.py"]) != 0:
        print("Generazione cover fallita.")
        return 1

    print("== 3/6 build sito ==")
    if _run(["tools/build_sito.py", "--check"]) != 0:
        print("Build fallita: routine fermata.")
        return 1

    print("== 4/6 pubblica ==")
    cmd = ["tools/pubblica_immagini.py"]
    if args.no_push:
        cmd.append("--no-push")
    try:
        genv = _git_env()
    except OSError:
        print(f"Token git assente ({TOKEN_FILE}): push impossibile.")
        return 1
    if _run(cmd, genv) != 0:
        print("Pubblicazione fallita.")
        return 1
    if args.no_push:
        print("(dry-run: niente controlli live, niente push)")
        return 0

    print("== 5/6 controlli live ==")
    base = "https://marylin12321.github.io/pinn-site/"
    ok = True
    for u in [base, base + "sitemap.xml", base + "guide/",
              base + "feed-casa-organizzazione-pratica.xml"]:
        vivo = _check_url(u)
        print(f"  {'✓' if vivo else '✗'} {u}")
        ok = ok and vivo
    if not ok:
        print("Alcuni URL non rispondono (magari Pages sta ancora pubblicando).")
        return 1

    print("== 6/6 coda guide ==")
    n, fino_a = _coda_guide()
    print(f"  guide programmate in coda: {n} (fino al {fino_a})")
    if n < 3:
        print("  ⚠️ coda quasi esaurita: chiedimi nuove guide!")
    if args.link:
        print("== controllo link Amazon ==")
        _run(["tools/check_link.py"])  # non blocca la routine: si legge il report
    else:
        print("  (per i link Amazon: python3 tools/routine.py --link)")
    print("\nROUTINE OK ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
