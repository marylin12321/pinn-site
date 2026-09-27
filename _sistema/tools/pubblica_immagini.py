#!/usr/bin/env python3
"""Pubblica le immagini generate + la landing page su GitHub Pages.

Il CSV di Pinterest ha bisogno di Media URL pubblici vivi: dopo ogni `genera`
le nuove immagini vanno sul repo Pages PRIMA dell'export. Questo script fa
l'intero ciclo in un colpo solo: copia → commit → push. Include anche
site/index.html (generata da tools/build_landing.py) nella root del repo,
così lo stesso URL fa da hosting immagini E da landing unica per i 4 profili.

Setup (una tantum, vedi docs/05-operazioni.md):
  1. crea repo PUBBLICO su GitHub (es. "pinn-site")
  2. git clone https://github.com/<tuoutente>/pinn-site.git ~/pinn-site
  3. metti il path in config/system.yaml → hosting.repo_locale
  4. GitHub: Settings → Pages → Source: main / (root)
  5. in ogni config/nicchie/*.yaml:
       media_base_url: "https://<tuoutente>.github.io/pinn-site/pin"

Uso (ogni ciclo, dopo `genera`):
  python3 tools/pubblica_immagini.py              # copia + commit + push
  python3 tools/pubblica_immagini.py --dry-run    # cosa farebbe, senza farlo
  python3 tools/pubblica_immagini.py --no-push    # copia+commit, push a mano
  python3 tools/pubblica_immagini.py --solo casa  # solo una nicchia
  python3 tools/pubblica_immagini.py --check      # verifica che le URL rispondano

Dopo la pubblicazione:  python3 src/main.py esporta   (CSV con Media URL già vivi)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
IMMAGINI = ROOT / "output" / "immagini"
ESTENSIONI = (".png", ".jpg", ".jpeg", ".webp")


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r


def _sorgenti(solo: str | None) -> list[Path]:
    """Solo i file immagine REALI (esclusa la cartella demo/)."""
    if not IMMAGINI.exists():
        return []
    return sorted(
        p for p in IMMAGINI.iterdir()
        if p.is_file() and p.suffix.lower() in ESTENSIONI
        and (solo is None or p.name.startswith(f"{solo}_"))
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=None, help="path clone locale (default: hosting.repo_locale)")
    ap.add_argument("--solo", default=None, help="solo una nicchia (es. casa)")
    ap.add_argument("--no-push", action="store_true", help="commit ma niente push")
    ap.add_argument("--no-prune", action="store_true", help="non cancellare file orfani nel repo")
    ap.add_argument("--dry-run", action="store_true", help="mostra il piano senza modificare nulla")
    ap.add_argument("--check", action="store_true", help="fa un HEAD sulle media_base_url alla fine")
    args = ap.parse_args()

    sistema = yaml.safe_load((ROOT / "config" / "system.yaml").read_text(encoding="utf-8")) or {}
    hosting = sistema.get("hosting") or {}
    raw_repo = args.repo or hosting.get("repo_locale") or ""
    if not str(raw_repo).strip():
        print("ERRORE: hosting.repo_locale non impostato (config/system.yaml).\n"
              "  Setup: git clone <repo-pages> ~/pinn-site  →  poi imposta\n"
              "  hosting:\n    repo_locale: /home/gabriele/pinn-site", file=sys.stderr)
        return 1
    repo_path = Path(str(raw_repo)).expanduser().resolve()
    sotto = (hosting.get("sotto_cartella") or "pin").strip("/")
    if not repo_path.is_dir() or not (repo_path / ".git").exists():
        print(f"ERRORE: {repo_path} non è un clone git valido.\n"
              "  Clone: git clone https://github.com/<tuoutente>/<repo>.git "
              f"{repo_path}", file=sys.stderr)
        return 1

    origine = _sorgenti(args.solo)

    # --- sito: tutto site/ in ricorsiva (index.html, privacy.html, covers/...) → root repo
    # Solo questi path sono gestiti: *.html in root + cartella covers/ (nostre al 100%).
    # README.md e il resto del repo non vengono mai toccati.
    site_dir = ROOT / "site"
    site_files = sorted(p for p in site_dir.rglob("*") if p.is_file()) if site_dir.exists() else []
    site_nuovi = [p for p in site_files
                  if not (repo_path / p.relative_to(site_dir)).exists()
                  or p.read_bytes() != (repo_path / p.relative_to(site_dir)).read_bytes()]
    if site_nuovi:
        print("sito: " + ", ".join(p.relative_to(site_dir).as_posix() for p in site_nuovi)
              + " da pubblicare/aggiornare")
    # prune: file nostri cancellati in locale spariscono anche dal repo.
    # Gestiti = tutto site/ (html, xml, txt, jpg...) TRANNE file estranei
    # (README.md, pin/, .github workflow, _sistema sorgenti, altri dotfile).
    gestiti = {p.relative_to(site_dir).as_posix() for p in site_files}
    orfani_sito: list[Path] = []
    for root, _dirs, files in os.walk(repo_path):
        for fn in files:
            rel = Path(root, fn).relative_to(repo_path).as_posix()
            if (rel == "README.md" or rel.startswith(("pin/", ".github/", "_sistema/"))
                    or Path(rel).parts[0].startswith(".")):
                continue
            if rel not in gestiti:
                orfani_sito.append(repo_path / rel)

    # --- sorgenti (tools/ config/ content/) → _sistema/ ---
    # La pipeline quotidiana di GitHub Actions ricostruisce il sito da lì anche
    # con il PC spento: le sorgenti vanno tenute allineate a ogni pubblicazione.
    SORGENTI = ("tools", "config", "content")
    sorg_diff: list[tuple[Path, Path]] = []  # (file locale, percorso relativo nel repo)
    for nome in SORGENTI:
        base = ROOT / nome
        if not base.exists():
            continue
        for p in sorted(x for x in base.rglob("*") if x.is_file()):
            if p.suffix == ".pyc" or "__pycache__" in p.parts:
                continue
            rel = Path("_sistema", nome) / p.relative_to(base)
            dst = repo_path / rel
            if not dst.exists() or dst.read_bytes() != p.read_bytes():
                sorg_diff.append((p, rel))
    sorgenti_orfani: list[Path] = []
    if (repo_path / "_sistema").exists():
        for root, dirs, files in os.walk(repo_path / "_sistema"):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in files:
                rel_repo = Path(root, fn)
                rel_locale = rel_repo.relative_to(repo_path).relative_to("_sistema")
                if not (ROOT / rel_locale).exists():
                    sorgenti_orfani.append(rel_repo)

    # commit locali mai pushati? (es. push precedente fallito: vanno inviati)
    avanti = _git(repo_path, "rev-list", "--count", "@{u}..HEAD", check=False)
    try:
        n_pendenti = int(avanti.stdout.strip())
    except ValueError:
        n_pendenti = 0  # nessun upstream: lo gestisce il push -u qui sotto

    if not origine and not site_nuovi and n_pendenti == 0 and not sorg_diff:
        print("Nessuna immagine reale in output/immagini/ e landing già aggiornata: niente da fare.\n"
              "  (Esegui `python3 src/main.py genera` per creare i pin.)")
        return 0
    if n_pendenti:
        print(f"{n_pendenti} commit locali mai pushati (es. push precedente fallito): li invio.")
    if not origine:
        print("Solo sito da pubblicare (nessuna immagine reale ancora).")

    destinazione = repo_path / sotto
    destinazione.mkdir(parents=True, exist_ok=True)

    # --- delta: cosa cambia ---
    da_copiare: list[Path] = []
    for p in origine:
        d = destinazione / p.name
        if not d.exists() or d.stat().st_size != p.stat().st_size:
            da_copiare.append(p)
    esistenti = {p.name for p in origine}
    # mai potare con --solo: i file fuori filtro sono di altre nicchie, non orfani!
    da_cancellare = ([] if (args.no_prune or args.solo or not origine) else
                     [p for p in destinazione.iterdir()
                      if p.is_file() and p.suffix.lower() in ESTENSIONI
                      and p.name not in esistenti])
    if args.solo:
        print(f"--solo {args.solo}: prune disattivato per sicurezza (solo aggiunte).")

    print(f"repo:  {repo_path}")
    print(f"dest:  {destinazione.relative_to(repo_path)}/")
    print(f"fonte: {len(origine)} immagini reali · da copiare: {len(da_copiare)} · "
          f"orfani da rimuovere: {len(da_cancellare)}")

    if args.dry_run:
        for p in da_copiare[:10]:
            print(f"  + {p.name}")
        if len(da_copiare) > 10:
            print(f"  + ... altre {len(da_copiare) - 10}")
        for p in da_cancellare[:5]:
            print(f"  - {p.name}")
        if site_nuovi:
            print("  + " + ", ".join(p.relative_to(site_dir).as_posix() for p in site_nuovi) + " (sito)")
        if orfani_sito:
            print("  - " + ", ".join(p.name for p in orfani_sito) + " (sito, orfani)")
        print("DRY-RUN: nessuna modifica.")
        return 0

    if site_nuovi:
        for p in site_nuovi:
            dst = repo_path / p.relative_to(site_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
        print("sito aggiornato: " + ", ".join(p.relative_to(site_dir).as_posix() for p in site_nuovi))
    if orfani_sito:
        for p in orfani_sito:
            p.unlink()
        print(f"sito: rimossi {len(orfani_sito)} orfani")
    if sorg_diff:
        for p, rel in sorg_diff:
            (repo_path / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, repo_path / rel)
        print(f"sorgenti aggiornate: {len(sorg_diff)} file → _sistema/")
    if sorgenti_orfani:
        for p in sorgenti_orfani:
            p.unlink()
        print(f"sorgenti: rimossi {len(sorgenti_orfani)} orfani")

    if (not da_copiare and not da_cancellare and not site_nuovi and not orfani_sito
            and not sorg_diff and not sorgenti_orfani):
        print("Già tutto aggiornato: niente da commitare.")
    else:
        for p in da_copiare:
            shutil.copy2(p, destinazione / p.name)
        for p in da_cancellare:
            p.unlink()
        print(f"copiati {len(da_copiare)} file" + (f", rimossi {len(da_cancellare)} orfani"
                                                  if da_cancellare else ""))

    # --- git: add SOLO cartella immagini + file sito (niente file estranei) ---
    # (n_pendenti già calcolato sopra; resta valido: qui in mezzo non si commita)
    percorsi = [sotto] + [p.relative_to(site_dir).as_posix() for p in site_files]
    # anche gli orfani vanno stagati (altrimenti le cancellazioni restano locali)
    percorsi += [o.relative_to(repo_path).as_posix() for o in orfani_sito
                 if o.relative_to(repo_path).as_posix() not in percorsi]
    # sorgenti per la pipeline GitHub (pathspec valido solo se la cartella c'è)
    if (repo_path / "_sistema").exists():
        percorsi.append("_sistema")
    if (repo_path / ".github").exists():
        percorsi.append(".github")  # workflow della pipeline quotidiana
    stato = _git(repo_path, "status", "--porcelain", *percorsi, check=False)
    if stato.returncode != 0:
        # MAI interpretare un errore git come "tutto pulito" (salterebbe il push in silenzio)
        print(f"ERRORE git status: {(stato.stderr or stato.stdout).strip()[:200]}", file=sys.stderr)
        return 1
    n_avanti = n_pendenti
    if stato.stdout.strip():
        _git(repo_path, "add", *percorsi)
        msg = (f"pin: immagini ({len(da_copiare)} nuove"
               f"{', sito aggiornato' if site_nuovi else ''}"
               f"{', sorgenti' if sorg_diff else ''}, "
               f"{datetime.now():%Y-%m-%d %H:%M})")
        _git(repo_path, "commit", "-m", msg)
        print(f"commit: {msg}")
        n_avanti += 1
    elif n_avanti == 0:
        print("Nessuna novità nel repo: push non necessario.")
    else:
        print(f"working tree pulito ma {n_avanti} commit locali da pushare "
              "(es. push precedente fallito).")
    if not stato.stdout.strip() and n_avanti == 0:
        pass  # niente da pushare
    elif args.no_push:
        print("--no-push: esegui a mano →  git -C", str(repo_path), "push")
    else:
        r = _git(repo_path, "push", check=False)
        if r.returncode != 0:
            if "does not match an existing remote ref" in r.stderr or "has no upstream" in r.stderr:
                r = _git(repo_path, "push", "-u", "origin", "HEAD", check=False)
            elif "fetch first" in r.stderr:
                # remote avanti (es. edit via API/GitHub web): rebase e riprova
                print("remote avanti di commit altrui: pull --rebase e riprovo...")
                rb = _git(repo_path, "pull", "--rebase", check=False)
                if rb.returncode != 0:
                    _git(repo_path, "rebase", "--abort", check=False)
                    print("CONFLITTO nel rebase: risolvi a mano dentro "
                          f"{repo_path} (git status, sistema, poi push).",
                          file=sys.stderr)
                    return 1
                r = _git(repo_path, "push", check=False)
            if r.returncode != 0:
                print(f"PUSH FALLITO: {r.stderr.strip()}\n"
                      f"  Riprova: git -C {repo_path} push", file=sys.stderr)
                return 1
        print("push ok ✓ (Pages pubblica in ~1 minuto)")

    # --- verifica URL vive ---
    if args.check:
        ok = tot = 0
        for nid in ({p.name.split("_")[0] for p in origine}):
            cfg = yaml.safe_load((ROOT / "config" / "nicchie" / f"{nid}.yaml").read_text(
                encoding="utf-8")) or {}
            base = (cfg.get("media_base_url") or "").strip()
            if not base:
                print(f"  ! {nid}: media_base_url vuoto")
                continue
            campione = next((p for p in origine if p.name.startswith(f"{nid}_")), None)
            if not campione:
                continue
            tot += 1
            url = f"{base.rstrip('/')}/{campione.name}"
            try:
                req = urllib.request.Request(url, method="HEAD",
                                             headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    if resp.status == 200:
                        ok += 1
                        print(f"  ✓ {url}")
                        continue
            except Exception as e:  # noqa: BLE001
                pass
            print(f"  ✗ {url} — non raggiungibile (Pages può richiedere qualche minuto"
                  f" al primo deploy; verifica il tuo media_base_url)")
        print(f"URL vive: {ok}/{tot}")
        if tot and ok < tot:
            return 1

    print("\nProssimo passo:  python3 src/main.py esporta   (i Media URL sono già vivi)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
