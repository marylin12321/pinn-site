#!/usr/bin/env python3
"""Assembla l'albero che la pipeline GitHub usa per ricostruire il sito.

Un unico posto che dice "cosa serve per fare il build", usato da due lati:

  1. la pipeline quotidiana, che senza questo script si ricostruiva da sola con
     una `cp -r` per riga dentro il YAML;
  2. `tools/pubblica_immagini.py --verifica-ci`, che prima di pushare rifà il
     build in una directory temporanea e si ferma se qualcosa manca.

Il secondo punto è il motivo per cui questo file esiste. Prima, un modulo di
cui un tool ha bisogno (è successo con `src/pendenze.py`, poi con
`src/url_base.py`) poteva mancare dalla copia e la pipeline se ne accorgeva
solo alle 08:15, di notte, con un run rosso. Ora la pagina-guida dei sorgenti
e la coda di pubblicazione sono verificate qui e nel `--verifica-ci`.

Uso:
  python3 _sistema/tools/prepara_ci.py --dest build          # in CI
  python3 tools/prepara_ci.py --repo /home/gabriele/pinn-site --dest /tmp/x
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Sorgenti spedite in _sistema/: ciò che il build deve poter importare e leggere.
# Elenco unico, niente magic: se aggiungi un modulo, lo aggiungi qui.
SORGENTI = ("tools", "config", "content", "src", "assets")

# Cose che già vivono nella root del repo e vanno messe sotto site/ perché il
# build le consumi da lì. Non sono fonti del sito, sono artefatti già costruiti
# che il build riusa invece di rifare (i printable richiederebbero Chrome).
RIUSO = (
    ("privacy.html", "privacy.html"),
    ("covers", "covers"),
    ("printable", "printable"),
    # Foto dei prodotti citati nelle guide: senza, le 15 pagine che le
    # mostrano verrebbero ricostruite con l'immagine rotta.
    ("prod", "prod"),
)

# `assets` nel repo contiene solo i 3 font che il codice carica: i 16 MB di
# fotografie di sfondo restano fuori, e con loro la possibilità di rigenerare le
# cover in CI. Le cover sono deterministiche e già committate, quindi in CI si
# riusano: vedi build_cover_guide.py.


def _copia(src: Path, dst: Path) -> int:
    """Copia albero o file, con il conteggio dei file copiati."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return sum(1 for p in dst.rglob("*") if p.is_file())
    shutil.copy2(src, dst)
    return 1


def prepara(repo: Path, dest: Path) -> int:
    """Assembla l'albero di build dentro `dest`. Ritorna i file copiati, -1 se errore."""
    if not (repo / "_sistema").is_dir():
        print(f"ERRORE: {repo} non contiene _sistema/: non è il repo del sito.",
              file=sys.stderr)
        return -1
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "site").mkdir(parents=True)
    n = 0
    for nome in SORGENTI:
        src = repo / "_sistema" / nome
        if not src.exists():
            print(f"ERRORE: manca _sistema/{nome}/ nel repo.", file=sys.stderr)
            return -1
        n += _copia(src, dest / nome)
    for origine, arrivo in RIUSO:
        src = repo / origine
        if not src.exists():
            print(f"  ! {origine} non c'è nel repo: il build potrebbe fallire")
            continue
        n += _copia(src, dest / "site" / arrivo)
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=None,
                    help="root del repo del sito (default: due livelli sopra questo file)")
    ap.add_argument("--dest", required=True, help="directory da creare con l'albero di build")
    args = ap.parse_args()
    repo = Path(args.repo).expanduser().resolve() if args.repo else \
        Path(__file__).resolve().parents[2]
    dest = Path(args.dest).expanduser().resolve()
    n = prepara(repo, dest)
    if n < 0:
        return 1
    print(f"albero di build pronto in {dest} ({n} file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
