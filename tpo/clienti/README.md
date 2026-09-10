# Gestione Clienti — Tower Power

Flusso completo: **Presentazione → Prova → Feedback → Ordine Ricorrente → SEMINA → Raccolta → Consegna → Pagamento**

## Struttura cartella

```
clienti/
├── README.md (questo file)
├── _templates/ (template JSON per nuovi clienti)
│   ├── cliente.json
│   ├── prova.json
│   └── ordine-ricorrente.json
├── [nome-cliente]/
│   ├── profilo.json (anagrafica + contatti)
│   ├── prove.json (storico prove concordate + feedback)
│   └── ordini-ricorrenti.json (ordini attivi ricorrenti)
```

## Flusso ordine ricorrente → SEMINA

1. **Ordine ricorrente attivo** in `[cliente]/ordini-ricorrenti.json`
2. **Script automatico** controlla ogni notte se è il giorno di consegna
3. **Se sì**: genera comando `tpo semina commission` per i lotti necessari
4. **SEMINA creata** → genera `SeminaTraceabilityCode` (AAA-GGMM-L)
5. **Consegna** → Pagamento

## Varieta disponibili

| VAR-ID | Denominazione | Codice |
|---|---|---|
| VAR-000001 | Afila | AFI |
| VAR-000002 | Rabano | RAB |
| VAR-000003 | Cilantro | CIL |
| VAR-000004 | Mizuna | MIZ |
| VAR-000005 | Hinojo | HIN |
| VAR-000006 | Basilico | ALB |
| VAR-000007 | Rucola | RUC |
| VAR-000008 | Pak Choi | PAK |
| VAR-000009 | Acetosella | ACE |
| VAR-000010 | Amaranto | AMA |
| VAR-000011 | Senape | MOS |
| VAR-000012 | Cavolo rosso | COL |
| VAR-000013 | Girasole | GIR |
| VAR-000014 | Lenticchia | LEN |
