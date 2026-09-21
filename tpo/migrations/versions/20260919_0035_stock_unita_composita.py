"""STOCK — chiave composita (varieta_id, unita_misura), non più singola per VARIETA.

Revision ID: 20260919_0035
Revises: 20260916_0034

Owner Decision (Matteo, 19/9/2026, conversazione in
docs/architecture/STOCK_UNITA_VENDITA_INTERA_PROPOSTA.md): "o facciamo tutto
in grammi o tutto in set, non me la sento di lasciare due varieta in grammi
e il resto in set". Questo supera l'"Alternativa scartata" di quel documento
(che escludeva la chiave composita) — la realtà operativa impone una sola
unità di misura VIVA per VARIETA da oggi in poi (SET ovunque), ma i 4
MOVIMENTI_MAGAZZINO storici in GRAM (MOV-000001..4, Afila/Cilantro) sono
immutabili per definizione (MOVIMENTO_CARICO_AUTHORITY_FREEZE.md) e restano
scritti per sempre nel registro. Poiché `tpo.movimenti_magazzino` ha una
foreign key RESTRICT verso `tpo.stock.(varieta_id, unita_misura)`, quella
riga STOCK in GRAM non può mai essere aggiornata/cancellata: l'unico modo
di avere SET vivo per Afila/Cilantro senza riscrivere la storia è permettere
una seconda riga STOCK per la stessa VARIETA, in un'altra unità.

Questa migrazione:
1. Aggiunge `tpo.allocazioni_stock.stock_unita_misura`, back-fillata dalla
   riga STOCK corrente di ciascuna VARIETA (oggi ancora univoca, quindi
   senza ambiguità), poi resa NOT NULL — necessaria perché anche
   `allocazioni_stock` ha una foreign key verso `tpo.stock`.
2. Rilassa la chiave primaria di `tpo.stock` da `varieta_id` a
   `(varieta_id, unita_misura)`: da oggi una VARIETA può avere più righe
   STOCK, una per unità di misura, mai due righe vive contemporaneamente
   per la stessa unità.
3. Ricrea le due foreign key esistenti (`movimenti_magazzino`,
   `allocazioni_stock`) verso la nuova chiave composita — nessun'altra
   authority referenzia `tpo.stock` (`replanning_snapshot_stock` referenzia
   `varieta.public_id`, mai `stock`, verificato in
   `20260811_0007_production_planning_allocations.py`).

Politica applicativa (fuori scope di questa migrazione, implementata nei
lettori): quando una VARIETA ha più righe STOCK vive, si preferisce quella
con `disponibile > 0`; se più di una è viva contemporaneamente è
un'anomalia da segnalare esplicitamente, mai da indovinare silenziosamente.

Nessuna riga MOVIMENTI_MAGAZZINO/RACCOLTE storica viene toccata da questa
migrazione — è additiva sullo schema, non tocca dati esistenti se non il
backfill (in sola lettura logica) di `allocazioni_stock.stock_unita_misura`.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260919_0035"
down_revision: str | Sequence[str] | None = "20260916_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"

unit_of_measure = postgresql.ENUM("SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # 1. allocazioni_stock guadagna l'unità: back-fill dalla riga STOCK
    #    corrente (oggi univoca per varieta_id), poi NOT NULL.
    op.add_column(
        "allocazioni_stock",
        sa.Column("stock_unita_misura", unit_of_measure, nullable=True),
        schema=SCHEMA,
    )
    op.execute(
        "UPDATE tpo.allocazioni_stock a SET stock_unita_misura = s.unita_misura "
        "FROM tpo.stock s WHERE s.varieta_id = a.stock_varieta_id"
    )
    op.alter_column("allocazioni_stock", "stock_unita_misura", nullable=False, schema=SCHEMA)

    # 2. Sgancia le due foreign key esistenti dalla chiave singola prima di
    #    poterla rimuovere (Postgres non permette di droppare un vincolo
    #    unique/PK finché una FK vi dipende ancora).
    op.drop_constraint(
        "fk_allocazioni_stock_stock_varieta", "allocazioni_stock", schema=SCHEMA, type_="foreignkey",
    )
    # Nome letterale, non introspezione a runtime: entrambi questi vincoli
    # sono inline/senza `name=` nella migrazione originale
    # (20260810_0004_production_execution_prerequisites.py, righe 148 e 177),
    # quindi Postgres li nomina con la sua convenzione di default
    # (<tabella>_pkey, <tabella>_<colonne>_fkey) — verificato leggendo quella
    # migrazione, e confermato dal testo esatto del ForeignKeyViolation reale
    # incontrato in produzione (Fatto 25). Una SELECT su pg_constraint qui
    # sarebbe stata comoda ma rompe la generazione SQL offline
    # (`alembic upgrade --sql`, bind.execute() non ha nulla da eseguire in
    # quella modalità) usata dai test di DDL del repo — scoperto da un run
    # pytest reale di Matteo (16 test falliti con `NoneType has no attribute
    # scalar_one`), corretto qui.
    op.drop_constraint(
        "movimenti_magazzino_varieta_id_unita_misura_fkey", "movimenti_magazzino",
        schema=SCHEMA, type_="foreignkey",
    )

    # 3. Rilassa la chiave di STOCK: via la PK a colonna singola e il
    #    vincolo unique ora orfano, dentro la nuova PK composita.
    op.drop_constraint("stock_pkey", "stock", schema=SCHEMA, type_="primary")
    op.drop_constraint("uq_stock_varieta_unita", "stock", schema=SCHEMA, type_="unique")
    op.create_primary_key("pk_stock", "stock", ["varieta_id", "unita_misura"], schema=SCHEMA)

    # 4. Ricrea entrambe le foreign key verso la nuova chiave composita.
    op.create_foreign_key(
        "fk_movimenti_magazzino_stock", "movimenti_magazzino", "stock",
        ["varieta_id", "unita_misura"], ["varieta_id", "unita_misura"],
        source_schema=SCHEMA, referent_schema=SCHEMA, onupdate="RESTRICT", ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_allocazioni_stock_stock_varieta", "allocazioni_stock", "stock",
        ["stock_varieta_id", "stock_unita_misura"], ["varieta_id", "unita_misura"],
        source_schema=SCHEMA, referent_schema=SCHEMA, onupdate="RESTRICT", ondelete="RESTRICT",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not context.is_offline_mode():
        multi_unit = bind.execute(
            sa.text(
                "SELECT count(*) FROM ("
                "SELECT varieta_id FROM tpo.stock GROUP BY varieta_id HAVING count(*) > 1"
                ") t"
            )
        ).scalar_one()
        if multi_unit:
            raise RuntimeError(
                "cannot downgrade: one or more VARIETA have more than one live tpo.stock row "
                "(one per unita_misura) and would violate the prior single-row-per-varieta "
                "primary key"
            )

    op.drop_constraint(
        "fk_allocazioni_stock_stock_varieta", "allocazioni_stock", schema=SCHEMA, type_="foreignkey",
    )
    op.drop_constraint(
        "fk_movimenti_magazzino_stock", "movimenti_magazzino", schema=SCHEMA, type_="foreignkey",
    )

    op.drop_constraint("pk_stock", "stock", schema=SCHEMA, type_="primary")
    op.create_primary_key("stock_pkey", "stock", ["varieta_id"], schema=SCHEMA)
    op.create_unique_constraint(
        "uq_stock_varieta_unita", "stock", ["varieta_id", "unita_misura"], schema=SCHEMA,
    )

    op.create_foreign_key(
        "movimenti_magazzino_varieta_id_unita_misura_fkey", "movimenti_magazzino", "stock",
        ["varieta_id", "unita_misura"], ["varieta_id", "unita_misura"],
        source_schema=SCHEMA, referent_schema=SCHEMA, onupdate="RESTRICT", ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_allocazioni_stock_stock_varieta", "allocazioni_stock", "stock",
        ["stock_varieta_id"], ["varieta_id"],
        source_schema=SCHEMA, referent_schema=SCHEMA, onupdate="RESTRICT", ondelete="RESTRICT",
    )

    op.drop_column("allocazioni_stock", "stock_unita_misura", schema=SCHEMA)
