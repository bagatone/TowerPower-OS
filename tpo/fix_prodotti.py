from pathlib import Path

path = Path("docs/registers/PRODOTTI.md")
text = path.read_text(encoding="utf-8")

text = text.replace(
    "La relazione con il Prodotto deve rimanere indiretta attraverso la Riga Ordine.",
    "Il Prodotto è raggiungibile attraverso il riferimento della Riga Ordine.\n\nI documenti congelati non definiscono per ASSEGNAZIONI un riferimento diretto obbligatorio al Prodotto."
)

text = text.replace(
    "La relazione con il Prodotto deve rimanere governata dai riferimenti applicabili attraverso Assegnazioni e Righe Ordine.",
    "Il Prodotto è raggiungibile attraverso i riferimenti applicabili alle Assegnazioni e alle Righe Ordine.\n\nI documenti congelati non definiscono per CONSEGNE un riferimento diretto obbligatorio al Prodotto."
)

path.write_text(text, encoding="utf-8")

print("OK")
