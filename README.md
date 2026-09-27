# Quattro Mondi

Sito del sistema Pinterest multi-nicchia, ospitato con GitHub Pages →
**https://marylin12321.github.io/pinn-site/**

Quattro profili, quattro mondi, un solo link:

| Profilo | Tema | Guide |
|---|---|---|
| @tuttoinordinecasa | casa e organizzazione | [casa](https://marylin12321.github.io/pinn-site/guide/casa-c01.html) |
| @coloridigusto | ricette e meal prep | [cibo](https://marylin12321.github.io/pinn-site/guide/cibo-c01.html) |
| @contiinordine | soldi, debiti, budget | [finanza](https://marylin12321.github.io/pinn-site/guide/fin-c01.html) |
| @piccolipassi | parenting | [parenting](https://marylin12321.github.io/pinn-site/guide/par-c01.html) |

## Cosa c'è qui dentro

- `index.html` — landing "Quattro Mondi", l'unico link usato sui 4 profili
- `guide/<slug>.html` — 40 guide, una pagina per ciascuna
- `printable/` — 7 strumenti scaricabili (PDF A4) per il mondo finanza
- `covers/` — copertine 1000×1500 dei pin, una per guida e per printable
- `feed2-<board>.xml` — 20 feed RSS, uno per board: è così che Pinterest pubblica da solo
- `sitemap.xml`, `robots.txt`, `privacy.html`
- `_sistema/` — le sorgenti del sito (tools, config, content, font)

## Il feed è il motore

Pinterest legge `feed2-*.xml` da questo stesso dominio e crea i pin da solo: non
serve aprire l'app, non serve toccare nulla. Ogni guida entra nel feed nel giorno
indicato da `pubblica_dal` nel suo frontmatter, e una volta pinnata esce dalla
coda. Se un feed si svuota, il build gli rimette dentro l'ultima guida già
pubblicata, perché Pinterest rifiuta un feed senza `<item>`.

Il sito si ricostruisce da solo ogni mattina alle 08:15 (workflow
`quotidiana.yml`): le guide in programma compaiono, senza che nessuno debba
preoccuparsene.

## Non scrivere qui a mano

Tutto quello che si vede è generato. Per cambiare qualcosa si toccano le
sorgenti in `_sistema/` e si rilancia il publish; il commit del giorno
successivo porta le modifiche qui. I file sono riproducibili: un rebuild senza
modifiche non produce nessun diff.

## Licenze

Le fotografie di sfondo vengono da Pexels (licenza Pexels, uso commerciale
libero). I prodotti citati arrivano da Amazon tramite il programma Affiliate:
i link sono affiliaati e le pagine lo dichiarano con `#adv`.
