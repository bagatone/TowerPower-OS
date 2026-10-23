"""Rendering PDF della BOLLA DI CONSEGNA.

Funzione pura: riceve il read model ``Bolla`` e restituisce i byte del PDF.
Non legge ne' scrive nulla. Tutto cio' che compare nel documento viene dal
database o dal file intestazione fornito dall'operatore: nessun dato
(indirizzi, P.IVA/NIF, prezzi) viene mai inventato. Le quantità che il
registro lotti non spiega sono stampate come "origine non tracciata", mai con
un codice.
"""
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from typing import Sequence
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from ...application.bolla_lettura.models import Bolla

LOCAL_TZ = ZoneInfo("Atlantic/Canary")
_UNITA = {"SET": "set", "GRAM": "g"}
_METODO = {"BONIFICO": "transferencia", "CONTANTI": "efectivo", "CARTA": "tarjeta",
           "BIZUM": "Bizum", "ALTRO": "otro"}


def format_quantity(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",") or "0"


def format_money(value: Decimal) -> str:
    """Importo con due decimali e virgola (es. 12,50 EUR); arrotondamento half-up al centesimo."""
    cents = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{cents:.2f}".replace(".", ",") + " EUR"


def _local(value: datetime) -> datetime:
    return value.astimezone(LOCAL_TZ) if value.tzinfo is not None else value


def estado_pagamento(bolla: Bolla) -> str:
    """Riga di stato pagamento della bolla: mai un dato non registrato."""
    pagamento = bolla.pagamento
    if pagamento is None:
        return "PENDIENTE DE PAGO"
    if pagamento.storico:
        return (f"PAGADO - registrado el {pagamento.data_pagamento.strftime('%d/%m/%Y')} "
                "(entrega anterior al control de pagos)")
    text = (f"PAGADO el {pagamento.data_pagamento.strftime('%d/%m/%Y')} - "
            f"{_METODO.get(pagamento.metodo, pagamento.metodo.lower())}")
    if pagamento.importo is not None:
        text += f" - {format_quantity(pagamento.importo)} EUR"
    return text


def render_bolla_pdf(
    bolla: Bolla, *, emittente: Sequence[str] = (), generata_il: datetime,
    compress: bool = True,
) -> bytes:
    styles = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=styles["Normal"], fontName="Helvetica",
                          fontSize=9, leading=12)
    small = ParagraphStyle("small", parent=base, fontSize=8, leading=10,
                           textColor=colors.HexColor("#555555"))
    title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold",
                           fontSize=16, leading=20)
    strong = ParagraphStyle("strong", parent=base, fontName="Helvetica-Bold")
    warn = ParagraphStyle("warn", parent=small, textColor=colors.HexColor("#8a4b00"))
    paid_style = ParagraphStyle("paid", parent=strong, fontSize=10,
                                textColor=colors.HexColor("#1b5e20"))
    unpaid_style = ParagraphStyle("unpaid", parent=strong, fontSize=10,
                                  textColor=colors.HexColor("#8a4b00"))

    def p(text: str, style=base) -> Paragraph:
        return Paragraph(escape(text), style)

    story: list = []
    header_lines = [str(line) for line in emittente if str(line).strip()] or ["Tower Power"]
    story.append(Paragraph(escape(header_lines[0]), strong))
    for line in header_lines[1:]:
        story.append(p(line, small))
    story.append(Spacer(1, 6 * mm))
    story.append(p("ALBARÁN DE ENTREGA", title))
    story.append(Spacer(1, 2 * mm))
    story.append(p(estado_pagamento(bolla), paid_style if bolla.pagamento else unpaid_style))
    story.append(Spacer(1, 3 * mm))

    effettiva = bolla.data_effettiva
    data_consegna = (_local(effettiva).strftime("%d/%m/%Y %H:%M") if effettiva
                     else bolla.data_prevista.strftime("%d/%m/%Y"))
    numero = " + ".join(bolla.consegne_unite) if bolla.consegne_unite else bolla.consegna_id.value
    if bolla.consegne_unite:
        giorni = sorted({r.data_consegna_origine for r in bolla.righe if r.data_consegna_origine})
        data_consegna = " - ".join(g.strftime("%d/%m/%Y") for g in giorni) or data_consegna
    meta = [
        [p("Número", small), p(numero, strong),
         p("Fecha de entrega", small), p(data_consegna, strong)],
        [p("Cliente", small), p(f"{bolla.cliente_denominazione} ({bolla.cliente_id})", strong),
         p("Destino", small), p(bolla.destinazione_fisica or "-", base)],
    ]
    if bolla.operatore:
        meta.append([p("Operador", small), p(bolla.operatore, base), "", ""])
    meta_table = Table(meta, colWidths=[22 * mm, 68 * mm, 28 * mm, 62 * mm])
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#999999")),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 5 * mm))

    con_prezzi = bolla.ha_prezzi        # i prezzi compaiono solo se il listino li ha: mai inventati
    rows: list[list] = [[p("Pos.", small), p("Variedad", small), p("Cantidad", small)]
                        + ([p("Precio unit.", small), p("Importe", small)] if con_prezzi else [])
                        + [p("Código de trazabilidad / procedencia", small)]]
    style_cmds: list[tuple] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#999999")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]
    for riga in bolla.righe:
        unit = _UNITA.get(riga.unita_misura, riga.unita_misura)
        qty = f"{format_quantity(riga.quantita)} {unit}"
        label = riga.varieta_denominazione + (" (rectificación)" if riga.rettifica else "")
        detail: list = []
        for origine in riga.origini:
            line = (f"{origine.codice_tracciabilita} - cosecha {origine.raccolta_id} del "
                    f"{_local(origine.data_raccolta).strftime('%d/%m/%Y')} - "
                    f"{format_quantity(origine.quantita)} {unit}")
            detail.append(p(line, base))
        if riga.quantita_senza_origine > 0:
            detail.append(p(
                f"Origen no trazado - {format_quantity(riga.quantita_senza_origine)} {unit}",
                warn,
            ))
        if not detail:
            detail.append(p("-", base))
        label_cell: list | Paragraph = p(label, strong)
        if riga.consegna_origine:
            giorno = (f" - {riga.data_consegna_origine.strftime('%d/%m/%Y')}"
                      if riga.data_consegna_origine else "")
            label_cell = [p(label, strong), p(f"{riga.consegna_origine}{giorno}", small)]
        riga_cells = [p(str(riga.posizione), base), label_cell, p(qty, base)]
        if con_prezzi:
            riga_cells += [
                p(format_money(riga.prezzo_unitario) if riga.prezzo_unitario is not None else "-", base),
                p(format_money(riga.importo) if riga.importo is not None else "-", base),
            ]
        rows.append(riga_cells + [detail])
        style_cmds.append(("LINEBELOW", (0, len(rows) - 1), (-1, len(rows) - 1), 0.25,
                           colors.HexColor("#cccccc")))
    widths = ([11 * mm, 32 * mm, 20 * mm, 24 * mm, 24 * mm, 69 * mm] if con_prezzi
              else [12 * mm, 42 * mm, 26 * mm, 100 * mm])
    lines_table = Table(rows, colWidths=widths, repeatRows=1)
    lines_table.setStyle(TableStyle(style_cmds))
    story.append(lines_table)
    if con_prezzi:
        story.append(Spacer(1, 3 * mm))
        total_label = "TOTAL" if bolla.prezzi_completi else "TOTAL (parcial: falta el precio de alguna línea)"
        total_table = Table([[p(total_label, strong), p(format_money(bolla.totale), strong)]],
                            colWidths=[87 * mm, 24 * mm], hAlign="LEFT")   # il totale sta sotto la colonna Importe
        total_table.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.HexColor("#999999")),
                                         ("ALIGN", (0, 0), (0, 0), "RIGHT")]))
        story.append(total_table)
    story.append(Spacer(1, 6 * mm))

    if bolla.righe_senza_origine:
        story.append(p(
            "Las cantidades indicadas como 'origen no trazado' no están asociadas a un "
            "código de trazabilidad porque el registro de lotes no las explica "
            "(existencias o entrega anteriores al registro de lotes).", warn))
        story.append(Spacer(1, 4 * mm))
    story.append(Spacer(1, 12 * mm))
    story.append(Table(
        [[p("Firma del receptor", small), "", p("Firma de quien entrega", small)],
         ["", "", ""]],
        colWidths=[80 * mm, 10 * mm, 80 * mm], rowHeights=[6 * mm, 14 * mm],
        style=TableStyle([("LINEBELOW", (0, 1), (0, 1), 0.5, colors.black),
                          ("LINEBELOW", (2, 1), (2, 1), 0.5, colors.black)]),
    ))

    def footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(
            15 * mm, 10 * mm,
            f"{numero} - generado el "
            f"{_local(generata_il).strftime('%d/%m/%Y %H:%M')} por Tower Power OS",
        )
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Página {doc.page}")
        canvas.restoreState()

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=18 * mm,
        title=f"Albarán de entrega {numero}", author="Tower Power OS",
        pageCompression=1 if compress else 0,
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
