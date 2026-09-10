"""Pagine HTML semplici generate dalla stessa struttura `to_jsonable` usata
dall'API JSON (vedi serialize.py).

Nessun template engine: una singola tabella generica, applicata
ricorsivamente, rende ogni boundary senza bisogno di una pagina scritta a
mano per ognuno dei 9 -- coerente con la scelta "pagine HTML semplici"
(non un cruscotto grafico) confermata dall'owner.

Lo stile visivo riusa gli stessi token (colori, font, pill di stato) già
validati nel mockup Artifact "Tower Power — Sala Operativa" (Fatto 1 della
roadmap): non introduce un secondo linguaggio grafico, applica quello già
approvato ai dati reali. Le euristiche di presentazione qui sotto (pill di
stato, colonne mono per identificativi, allineamento numerico) leggono
esclusivamente la FORMA del valore già serializzato da `to_jsonable`
(maiuscolo/underscore, pattern PREFISSO-NNNNNN, numero puro...) — nessuna
conoscenza di dominio è codificata (nessun nome di boundary/campo/stato
specifico è richiesto da questo modulo per funzionare)."""
from __future__ import annotations

import re
from html import escape
from typing import Any, Callable, Iterable

_STYLE = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --surface: #F6F9F5;
  --surface-raised: #FFFFFF;
  --surface-sunken: #EEF3EC;
  --ink: #172A1D;
  --ink-muted: #56685B;
  --ink-faint: #8A9A8D;
  --border: #DDE6D9;
  --border-soft: #E9EFE6;

  --brand: #2B7A4F;
  --brand-strong: #1E5C3A;
  --brand-soft: #E3F1E6;

  --good: #2E8F52;
  --good-soft: #E3F3E7;
  --warning: #C08A1A;
  --warning-soft: #FBF0DA;
  --critical: #C13B4F;
  --critical-soft: #FBE6E9;
  --neutral: #3E6FA6;
  --neutral-soft: #E6EEF6;

  --shadow: 0 1px 2px rgba(23,42,29,0.06), 0 6px 20px -8px rgba(23,42,29,0.14);
  --radius: 12px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --surface: #12180F; --surface-raised: #1A2318; --surface-sunken: #0E130C;
    --ink: #EAF0E6; --ink-muted: #A3B39F; --ink-faint: #6E7D6B;
    --border: #2B382A; --border-soft: #212C1F;
    --brand: #4CAF74; --brand-strong: #6FC490; --brand-soft: #1D3226;
    --good: #2F9A6B; --good-soft: #17301F; --warning: #BC862A; --warning-soft: #33290E;
    --critical: #C33F52; --critical-soft: #33161A; --neutral: #4A85C9; --neutral-soft: #172231;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 10px 28px -10px rgba(0,0,0,0.5);
  }
}
:root[data-theme="dark"] {
  --surface: #12180F; --surface-raised: #1A2318; --surface-sunken: #0E130C;
  --ink: #EAF0E6; --ink-muted: #A3B39F; --ink-faint: #6E7D6B;
  --border: #2B382A; --border-soft: #212C1F;
  --brand: #4CAF74; --brand-strong: #6FC490; --brand-soft: #1D3226;
  --good: #2F9A6B; --good-soft: #17301F; --warning: #BC862A; --warning-soft: #33290E;
  --critical: #C33F52; --critical-soft: #33161A; --neutral: #4A85C9; --neutral-soft: #172231;
  --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 10px 28px -10px rgba(0,0,0,0.5);
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--surface); color: var(--ink);
  font-family: 'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif;
  -webkit-font-smoothing: antialiased;
}
.mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; }
h1, h2 { font-family: 'Fraunces', Georgia, serif; text-wrap: balance; font-weight: 600; }

header.top {
  background: var(--surface-raised); border-bottom: 1px solid var(--border);
  padding: 14px 24px;
}
.top-inner { max-width: 1180px; margin: 0 auto; }
.brandmark { display: flex; align-items: center; gap: 12px; text-decoration: none; color: inherit; }
.brandmark .glyph {
  width: 34px; height: 34px; border-radius: 9px; flex: none;
  background: linear-gradient(155deg, var(--brand) 0%, var(--brand-strong) 100%);
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-family: 'Fraunces', serif; font-weight: 600; font-size: 16px;
}
.brandmark .name { font-size: 17px; font-weight: 600; line-height: 1.1; }
.brandmark .name small { display: block; font-family: 'IBM Plex Sans', sans-serif; font-weight: 500; font-size: 11.5px; color: var(--ink-muted); margin-top: 1px; }
nav.crumbs {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px;
}
nav.crumbs a {
  color: var(--ink-muted); text-decoration: none; font-size: 12.5px; font-weight: 500;
  padding: 5px 10px; border-radius: 100px; border: 1px solid transparent;
  white-space: nowrap;
}
nav.crumbs a:hover { background: var(--surface-sunken); color: var(--ink); border-color: var(--border); }

main { max-width: 1180px; margin: 0 auto; padding: 26px 24px 64px; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 22px 0 10px; }
.subtitle { color: var(--ink-muted); margin: 0 0 20px; font-size: 13px; max-width: 60ch; }
.count { color: var(--ink-faint); font-weight: 500; font-size: 14px; font-family: 'IBM Plex Sans', sans-serif; }

.panel {
  background: var(--surface-raised); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow);
  margin-bottom: 20px; overflow: hidden;
}
.table-scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
thead th {
  text-align: left; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--ink-faint); font-weight: 600; padding: 11px 14px; white-space: nowrap;
  border-bottom: 1px solid var(--border);
}
tbody td { padding: 10px 14px; border-bottom: 1px solid var(--border-soft); vertical-align: middle; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: var(--surface-sunken); }
td.num { text-align: right; }

table table { margin: 0; font-size: 12.5px; background: var(--surface-sunken); border-radius: 8px; overflow: hidden; }
table table thead th { padding: 7px 10px; }
table table tbody td { padding: 6px 10px; }

.kv { background: transparent; }
.kv td:first-child {
  font-weight: 600; width: 15rem; color: var(--ink-muted); font-size: 12px;
  text-transform: uppercase; letter-spacing: 0.03em; border-bottom: 1px solid var(--border-soft);
  background: transparent; vertical-align: top; padding-top: 12px;
}
.kv td:last-child { border-bottom: 1px solid var(--border-soft); }
.kv tr:last-child td { border-bottom: none; }

.idcell { font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: var(--ink-muted); }
.numcell { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; }
.muted { color: var(--ink-faint); }
a { color: var(--brand-strong); }
a:hover { text-decoration: none; }

.pill {
  display: inline-flex; align-items: center; padding: 2.5px 9px; border-radius: 100px;
  font-size: 11px; font-weight: 600; white-space: nowrap; line-height: 1.5;
}
.pill.good { background: var(--good-soft); color: var(--good); }
.pill.warning { background: var(--warning-soft); color: var(--warning); }
.pill.critical { background: var(--critical-soft); color: var(--critical); }
.pill.neutral { background: var(--neutral-soft); color: var(--neutral); }

.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; margin-bottom: 26px; }
.card-group .group-label {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600;
  color: var(--ink-faint); margin: 26px 0 10px;
}
.card-group:first-child .group-label { margin-top: 0; }
a.nav-card {
  display: block; background: var(--surface-raised); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow); padding: 14px 16px;
  text-decoration: none; color: var(--ink);
}
a.nav-card:hover { border-color: var(--brand); }
a.nav-card .label { font-weight: 600; font-size: 14.5px; }
a.nav-card .path { display: block; margin-top: 3px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--ink-faint); }

.error-box {
  background: var(--critical-soft); border: 1px solid color-mix(in srgb, var(--critical) 35%, transparent);
  padding: 16px; border-radius: var(--radius);
}
.error-box .badge {
  display: inline-block; padding: 2px 9px; border-radius: 100px; font-size: 11px; font-weight: 700;
  background: var(--surface-raised); color: var(--critical); font-family: 'IBM Plex Mono', monospace;
  margin-bottom: 8px;
}
.error-box p { margin: 0; color: var(--ink); }

footer.foot {
  max-width: 1180px; margin: 0 auto; padding: 18px 24px 40px; font-size: 12px; color: var(--ink-faint);
}

@media (max-width: 640px) {
  main { padding: 20px 16px 48px; }
  header.top { padding: 12px 16px; }
}
"""

_NAV_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Anagrafiche", (
        ("Clienti", "/clienti"),
        ("Varietà", "/varieta"),
        ("Sementi", "/sementi"),
        ("Lotti seme", "/lotti-seme"),
    )),
    ("Produzione", (
        ("Semine", "/semine"),
    )),
    ("Magazzino", (
        ("Stock", "/magazzino/stock"),
        ("Articoli", "/magazzino/articoli"),
        ("Movimenti", "/magazzino/movimenti"),
    )),
    ("Fornitura", (
        ("Programmi fornitura", "/programmi-fornitura"),
        ("Ordini", "/ordini"),
        ("Consegne", "/consegne"),
        ("Assegnazioni fisiche", "/assegnazioni-fisiche"),
    )),
    ("Finanze", (
        ("Fatture", "/fatture"),
        ("Incassi", "/incassi"),
        ("Uscite", "/uscite"),
    )),
    ("Sistema", (
        ("Run", "/run"),
    )),
)

# Nav piatta per l'header, presente su ogni pagina (stessa lista usata sopra).
_NAV: tuple[tuple[str, str], ...] = tuple(
    link for _group, links in _NAV_GROUPS for link in links
)

# Euristiche lessicali generiche di presentazione: leggono solo la stringa
# già serializzata, non introducono alcuna conoscenza di dominio nuova.
_PILL_GOOD = {
    "ATTIVO", "ATTIVA", "EVASO", "EVASA", "CONSEGNATA", "CONSEGNATO",
    "SUCCESS", "COMPLETATO", "COMPLETATA", "PRONTA_ALLA_RACCOLTA",
    "APPROVATA", "APPROVATO",
}
_PILL_CRITICAL = {
    "ANNULLATO", "ANNULLATA", "FAILURE", "RIFIUTATO", "RIFIUTATA",
    "SCADUTO", "SCADUTA", "FALLITO", "FALLITA",
}
_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]{6,}$|^[0-9]{4}/[0-9]{4}$")
_NUMBER_PATTERN = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
_TOKEN_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")


def _label(field_name: str) -> str:
    words = field_name.replace("_", " ").split(" ")
    if not words:
        return field_name
    return " ".join([words[0].capitalize(), *words[1:]])


def _pill(text: str) -> str:
    if text in _PILL_GOOD:
        variant = "good"
    elif text in _PILL_CRITICAL:
        variant = "critical"
    else:
        variant = "neutral"
    label = text.replace("_", " ").capitalize()
    return f'<span class="pill {variant}">{escape(label)}</span>'


def _format_scalar(value: Any) -> str:
    if value is None:
        return '<span class="muted">—</span>'
    if isinstance(value, bool):
        return _pill("Sì" if value else "No")
    text = str(value)
    if _ID_PATTERN.match(text):
        return f'<span class="idcell">{escape(text)}</span>'
    if _NUMBER_PATTERN.match(text):
        return f'<span class="numcell">{escape(text)}</span>'
    if len(text) >= 2 and _TOKEN_PATTERN.match(text):
        return _pill(text)
    return escape(text)


def render_value(value: Any) -> str:
    """Rende ricorsivamente un valore già passato da `to_jsonable`
    (dict/list/scalare) come tabella HTML annidata."""

    if isinstance(value, dict):
        if not value:
            return '<span class="muted">—</span>'
        rows = "".join(
            f"<tr><td>{escape(_label(key))}</td><td>{render_value(item)}</td></tr>"
            for key, item in value.items()
        )
        return f'<table class="kv">{rows}</table>'
    if isinstance(value, list):
        if not value:
            return '<span class="muted">(nessuno)</span>'
        if all(isinstance(item, dict) for item in value):
            columns: list[str] = []
            for item in value:
                for key in item.keys():
                    if key not in columns:
                        columns.append(key)
            head = "".join(f"<th>{escape(_label(col))}</th>" for col in columns)
            body = "".join(
                "<tr>"
                + "".join(f"<td>{render_value(item.get(col))}</td>" for col in columns)
                + "</tr>"
                for item in value
            )
            return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
        return ", ".join(_format_scalar(item) for item in value)
    return _format_scalar(value)


def _page(title: str, body: str) -> str:
    crumbs = "".join(f'<a href="{href}">{escape(label)}</a>' for label, href in _NAV)
    return (
        "<!doctype html><html lang=\"it\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)} · Tower Power OS</title><style>{_STYLE}</style></head>"
        "<body>"
        '<header class="top"><div class="top-inner">'
        '<a class="brandmark" href="/">'
        '<span class="glyph">TP</span>'
        '<span class="name">Tower Power OS<small>Sala Operativa — dati reali di produzione</small></span>'
        "</a>"
        f'<nav class="crumbs">{crumbs}</nav>'
        "</div></header>"
        f"<main>{body}</main>"
        '<footer class="foot">Tower Power Operations — TPO · sola lettura, Fase 1 OPERATIONAL_WEB_ADAPTER</footer>'
        "</body></html>"
    )


def render_table(
    items: list[dict],
    *,
    detail_path: Callable[[dict], str] | None = None,
    id_field: str | None = None,
) -> str:
    """Rende una lista di dict (già passati da `to_jsonable`) come tabella
    HTML, con la colonna `id_field` linkata a `detail_path` se fornita.
    Riusata sia da `render_list_page` sia dalle pagine multi-sezione
    (es. MAGAZZINO, che mostra due elenchi -- stock varietà e articoli --
    nella stessa pagina)."""

    if not items:
        return '<p class="muted">Nessun elemento presente.</p>'

    columns: list[str] = []
    for item in items:
        for key in item.keys():
            if key not in columns:
                columns.append(key)

    head = "".join(f"<th>{escape(_label(col))}</th>" for col in columns)
    rows_html = []
    for item in items:
        cells = []
        for col in columns:
            rendered = render_value(item.get(col))
            raw = item.get(col)
            css_class = ""
            if detail_path is not None and id_field is not None and col == id_field:
                href = escape(detail_path(item))
                rendered = f'<a href="{href}">{rendered}</a>'
            elif (
                isinstance(raw, (int, float)) and not isinstance(raw, bool)
            ) or (isinstance(raw, str) and _NUMBER_PATTERN.match(raw)):
                css_class = ' class="num"'
            cells.append(f"<td{css_class}>{rendered}</td>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    return (
        '<div class="panel"><div class="table-scroll">'
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"
        "</div></div>"
    )


def render_list_page(
    *,
    title: str,
    subtitle: str,
    items: list[dict],
    detail_path: Callable[[dict], str] | None = None,
    id_field: str | None = None,
) -> str:
    body = (
        f"<h1>{escape(title)} <span class=\"count\">({len(items)})</span></h1>"
        f"<p class=\"subtitle\">{escape(subtitle)}</p>"
        f"{render_table(items, detail_path=detail_path, id_field=id_field)}"
    )
    return _page(title, body)


def render_detail_page(*, title: str, subtitle: str, item: dict) -> str:
    body = (
        f"<h1>{escape(title)}</h1><p class=\"subtitle\">{escape(subtitle)}</p>"
        f'<div class="panel" style="padding: 4px 14px;">{render_value(item)}</div>'
    )
    return _page(title, body)


def render_page(title: str, body: str) -> str:
    """Punto d'estensione pubblico per pagine multi-sezione composte a mano
    (es. MAGAZZINO/STOCK, che unisce due tabelle in un'unica pagina)."""

    return _page(title, body)


def render_index_page() -> str:
    groups_html = []
    for group_label, links in _NAV_GROUPS:
        cards = "".join(
            f'<a class="nav-card" href="{href}">'
            f'<span class="label">{escape(label)}</span>'
            f'<span class="path">{escape(href)}</span>'
            "</a>"
            for label, href in links
        )
        groups_html.append(
            f'<div class="card-group"><div class="group-label">{escape(group_label)}</div>'
            f'<div class="card-grid">{cards}</div></div>'
        )
    body = (
        "<h1>Tower Power OS — Sala Operativa</h1>"
        '<p class="subtitle">Fase 1 OPERATIONAL_WEB_ADAPTER: query a sola lettura sui '
        "dati reali di produzione. Nessuna scrittura avviene da questa pagina.</p>"
        f"{''.join(groups_html)}"
    )
    return _page("Sala Operativa", body)


def render_error_page(status: int, code: str, message: str) -> str:
    body = (
        f"<h1>Errore {status}</h1>"
        f'<div class="error-box"><span class="badge">{escape(code)}</span>'
        f"<p>{escape(message)}</p></div>"
    )
    return _page(f"Errore {status}", body)
