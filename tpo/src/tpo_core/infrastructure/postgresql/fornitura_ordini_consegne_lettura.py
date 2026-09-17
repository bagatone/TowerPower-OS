"""Reader PostgreSQL a sola lettura per FORNITURA/ORDINI/CONSEGNE/ASSEGNAZIONE_FISICA V1.

Autorita: docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md.
Nessuna scrittura. Vedi il docstring di
application/fornitura_ordini_consegne_lettura/models.py per le scelte di
scope (solo versione corrente di PROGRAMMA_FORNITURA, righe referenziate
per posizione anziche' per id pubblico non sempre presente, correzioni di
RIGA_CONSEGNA esposte come flag senza risolvere il riferimento originale).
"""
from __future__ import annotations

from collections import defaultdict

import psycopg

from ...application.fornitura_ordini_consegne_lettura.models import (
    AssegnazioneFisica, Consegna, ElencoAssegnazioniFisiche, ElencoConsegne, ElencoOrdini,
    ElencoProgrammiFornitura, Ordine, ProgrammaFornitura, RichiediElencoAssegnazioniFisiche,
    RichiediElencoConsegne, RichiediElencoOrdini, RichiediElencoProgrammiFornitura,
    RigaConsegna, RigaOrdine, RigaProgrammaFornitura,
)
from ...domain.identifiers import (
    AssegnazioneFisicaId, ClienteId, ConsegnaId, OrdineId, ProgrammaFornituraId, RaccoltaId,
    VarietaId,
)
from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLError

_SELECT_PROGRAMMI = (
    "SELECT pf.public_id, cl.public_id, cl.denominazione, pfv.id, pfv.numero_versione, "
    "pfv.stato, pfv.data_inizio, pfv.data_fine, pfv.finestra_operativa_giorni, pfv.valida_dal, "
    "pf.data_ripresa_prevista "
    "FROM tpo.programmi_fornitura_versioni pfv "
    "JOIN tpo.programmi_fornitura pf ON pf.id = pfv.programma_fornitura_id "
    "JOIN tpo.clienti cl ON cl.id = pfv.cliente_id "
    "WHERE pfv.valida_al IS NULL AND pfv.voided_at IS NULL"
)
_SELECT_RIGHE_PROGRAMMA = (
    "SELECT rpf.id, rpf.programma_versione_id, rpf.posizione, v.public_id, v.denominazione, "
    "rpf.quantita, rpf.unita_misura, rpf.tipo_ricorrenza, rpf.intervallo_giorni "
    "FROM tpo.righe_programma_fornitura rpf JOIN tpo.varieta v ON v.id = rpf.varieta_id"
)
_SELECT_GIORNI_PROGRAMMA = (
    "SELECT riga_programma_id, giorno_iso FROM tpo.righe_programma_giorni"
)
_SELECT_ORDINI = (
    "SELECT o.public_id, cl.public_id, cl.denominazione, pf.public_id, o.data_ordine, "
    "o.data_consegna_prevista, o.stato, o.tipo_creazione "
    "FROM tpo.ordini o JOIN tpo.clienti cl ON cl.id = o.cliente_id "
    "LEFT JOIN tpo.programmi_fornitura pf ON pf.id = o.programma_fornitura_id"
)
_SELECT_RIGHE_ORDINE = (
    "SELECT o.public_id, ro.posizione, v.public_id, v.denominazione, ro.quantita, "
    "ro.unita_misura FROM tpo.righe_ordine ro "
    "JOIN tpo.ordini o ON o.id = ro.ordine_id JOIN tpo.varieta v ON v.id = ro.varieta_id"
)
_SELECT_CONSEGNE = (
    "SELECT c.public_id, cl.public_id, cl.denominazione, c.stato, c.data_prevista, "
    "c.data_effettiva, c.destinazione_fisica "
    "FROM tpo.consegne c JOIN tpo.clienti cl ON cl.id = c.cliente_id"
)
_SELECT_ORDINI_CONSEGNA = (
    "SELECT c.public_id, o.public_id FROM tpo.consegne_ordini co "
    "JOIN tpo.consegne c ON c.id = co.consegna_id JOIN tpo.ordini o ON o.id = co.ordine_id"
)
_SELECT_RIGHE_CONSEGNA = (
    "SELECT c.public_id, rc.posizione, v.public_id, v.denominazione, rc.quantita, "
    "rc.unita_misura, rc.rettifica_riga_consegna_id "
    "FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id = rc.consegna_id "
    "JOIN tpo.varieta v ON v.id = rc.varieta_id"
)
_SELECT_ASSEGNAZIONI = (
    "SELECT af.public_id, r.public_id, o.public_id, ro.posizione, c.public_id, "
    "af.quantita_assegnata, af.unita_misura, af.effective_at, af.motivo "
    "FROM tpo.assegnazioni_fisiche af "
    "JOIN tpo.raccolte r ON r.id = af.raccolta_id "
    "JOIN tpo.righe_ordine ro ON ro.id = af.riga_ordine_id "
    "JOIN tpo.ordini o ON o.id = ro.ordine_id "
    "LEFT JOIN tpo.consegne c ON c.id = af.consegna_id"
)


class PostgreSQLFornituraOrdiniConsegneLetturaReader:
    def __init__(self, factory: PostgreSQLConnectionFactory) -> None:
        self._factory = factory

    def programmi_fornitura(
        self, query: RichiediElencoProgrammiFornitura
    ) -> ElencoProgrammiFornitura:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_PROGRAMMI} ORDER BY cl.denominazione")
                programmi_rows = cursor.fetchall()
                cursor.execute(f"{_SELECT_RIGHE_PROGRAMMA} ORDER BY rpf.posizione")
                righe_rows = cursor.fetchall()
                cursor.execute(_SELECT_GIORNI_PROGRAMMA)
                giorni_rows = cursor.fetchall()
            giorni_per_riga: dict[int, list[int]] = defaultdict(list)
            for riga_programma_id, giorno_iso in giorni_rows:
                giorni_per_riga[riga_programma_id].append(giorno_iso)
            righe_per_versione: dict[int, list[RigaProgrammaFornitura]] = defaultdict(list)
            for row in righe_rows:
                (riga_id, versione_id, posizione, varieta_public_id, varieta_denominazione,
                 quantita, unita_misura, tipo_ricorrenza, intervallo_giorni) = row
                righe_per_versione[versione_id].append(RigaProgrammaFornitura(
                    posizione, VarietaId(varieta_public_id), varieta_denominazione, quantita,
                    unita_misura, tipo_ricorrenza, intervallo_giorni,
                    tuple(sorted(giorni_per_riga.get(riga_id, []))),
                ))
            programmi = tuple(
                ProgrammaFornitura(
                    ProgrammaFornituraId(pf_public_id), ClienteId(cl_public_id), cl_denominazione,
                    numero_versione, stato, data_inizio, data_fine, finestra_operativa_giorni,
                    valida_dal, tuple(righe_per_versione.get(versione_id, [])),
                    data_ripresa_prevista,
                )
                for (pf_public_id, cl_public_id, cl_denominazione, versione_id, numero_versione,
                     stato, data_inizio, data_fine, finestra_operativa_giorni, valida_dal,
                     data_ripresa_prevista)
                in programmi_rows
            )
            return ElencoProgrammiFornitura(programmi)
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura PROGRAMMI_FORNITURA PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def ordini(self, query: RichiediElencoOrdini) -> ElencoOrdini:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_ORDINI} ORDER BY o.data_ordine DESC")
                ordini_rows = cursor.fetchall()
                cursor.execute(f"{_SELECT_RIGHE_ORDINE} ORDER BY ro.posizione")
                righe_rows = cursor.fetchall()
            righe_per_ordine: dict[str, list[RigaOrdine]] = defaultdict(list)
            for ordine_public_id, posizione, varieta_public_id, varieta_denominazione, \
                    quantita, unita_misura in righe_rows:
                righe_per_ordine[ordine_public_id].append(RigaOrdine(
                    posizione, VarietaId(varieta_public_id), varieta_denominazione, quantita,
                    unita_misura,
                ))
            ordini = tuple(
                Ordine(
                    OrdineId(o_public_id), ClienteId(cl_public_id), cl_denominazione,
                    ProgrammaFornituraId(pf_public_id) if pf_public_id is not None else None,
                    data_ordine, data_consegna_prevista, stato, tipo_creazione,
                    tuple(righe_per_ordine.get(o_public_id, [])),
                )
                for (o_public_id, cl_public_id, cl_denominazione, pf_public_id, data_ordine,
                     data_consegna_prevista, stato, tipo_creazione) in ordini_rows
            )
            return ElencoOrdini(ordini)
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura ORDINI PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def consegne(self, query: RichiediElencoConsegne) -> ElencoConsegne:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_CONSEGNE} ORDER BY c.data_prevista DESC")
                consegne_rows = cursor.fetchall()
                cursor.execute(f"{_SELECT_ORDINI_CONSEGNA} ORDER BY co.posizione")
                ordini_rows = cursor.fetchall()
                cursor.execute(f"{_SELECT_RIGHE_CONSEGNA} ORDER BY rc.posizione")
                righe_rows = cursor.fetchall()
            ordini_per_consegna: dict[str, list[OrdineId]] = defaultdict(list)
            for consegna_public_id, ordine_public_id in ordini_rows:
                ordini_per_consegna[consegna_public_id].append(OrdineId(ordine_public_id))
            righe_per_consegna: dict[str, list[RigaConsegna]] = defaultdict(list)
            for consegna_public_id, posizione, varieta_public_id, varieta_denominazione, \
                    quantita, unita_misura, rettifica_id in righe_rows:
                righe_per_consegna[consegna_public_id].append(RigaConsegna(
                    posizione, VarietaId(varieta_public_id), varieta_denominazione, quantita,
                    unita_misura, rettifica_id is not None,
                ))
            consegne = tuple(
                Consegna(
                    ConsegnaId(c_public_id), ClienteId(cl_public_id), cl_denominazione, stato,
                    data_prevista, data_effettiva, destinazione_fisica,
                    tuple(ordini_per_consegna.get(c_public_id, [])),
                    tuple(righe_per_consegna.get(c_public_id, [])),
                )
                for (c_public_id, cl_public_id, cl_denominazione, stato, data_prevista,
                     data_effettiva, destinazione_fisica) in consegne_rows
            )
            return ElencoConsegne(consegne)
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura CONSEGNE PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    def assegnazioni_fisiche(
        self, query: RichiediElencoAssegnazioniFisiche
    ) -> ElencoAssegnazioniFisiche:
        connection = self._factory.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"{_SELECT_ASSEGNAZIONI} ORDER BY af.effective_at DESC")
                rows = cursor.fetchall()
            assegnazioni = tuple(
                AssegnazioneFisica(
                    AssegnazioneFisicaId(af_public_id), RaccoltaId(raccolta_public_id),
                    OrdineId(ordine_public_id), posizione,
                    ConsegnaId(consegna_public_id) if consegna_public_id is not None else None,
                    quantita_assegnata, unita_misura, effective_at, motivo,
                )
                for (af_public_id, raccolta_public_id, ordine_public_id, posizione,
                     consegna_public_id, quantita_assegnata, unita_misura, effective_at, motivo)
                in rows
            )
            return ElencoAssegnazioniFisiche(assegnazioni)
        except psycopg.Error as exc:
            raise PostgreSQLError("Lettura ASSEGNAZIONI_FISICHE PostgreSQL fallita.") from exc
        finally:
            self._release(connection)

    @staticmethod
    def _release(connection) -> None:
        try:
            connection.rollback()
        except Exception:
            pass
        try:
            connection.close()
        except Exception:
            pass
