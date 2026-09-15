"""RACCOLTA CORREZIONE — rettifica di sola annotazione (destinazione_prevista).

Revision ID: 20260915_0033
Revises: 20260905_0032

Estende il vincolo introdotto da 20260903_0027_raccolta_correzione_authority.py
(`ck_raccolte_ordinary_or_correction`) per ammettere un nuovo caso, approvato
da Owner Decision D2 di
docs/architecture/RACCOLTA_DESTINAZIONE_PREVISTA_CORREZIONE_PROPOSTA.md
(conversazione Owner 2026-09-10), registrato in
docs/architecture/RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md §11: una rettifica
(`rettifica_raccolta_id IS NOT NULL`) con quantità **zero** è ammessa quando
accompagnata da `destinazione_prevista` non nullo — annota un evento RACCOLTA
(es. "PROVA", "OMAGGIO") senza alterarne la quantità netta. Senza tale
annotazione resta vietata (sarebbe una rettifica senza alcun effetto e senza
causale), invariato rispetto a 20260903_0027.

Il vincolo composito applicativo (application/raccolta/models.py,
`_signed_quantity(..., allow_zero=...)`) fa già fail-closed su questo caso
prima di arrivare al database; questa migrazione allinea il CHECK di
PostgreSQL, che è l'autorità ultima (fail-closed anche per scritture dirette
fuori dal boundary applicativo).

Migrazione additiva e retrocompatibile: nessuna riga esistente può violare il
nuovo vincolo, che è strettamente più permissivo del precedente (ogni riga
che soddisfaceva il vecchio CHECK soddisfa anche il nuovo).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260915_0033"
down_revision: str | Sequence[str] | None = "20260905_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

OLD_CHECK = (
    "(rettifica_raccolta_id IS NULL AND quantita > 0) OR "
    "(rettifica_raccolta_id IS NOT NULL AND quantita <> 0)"
)
NEW_CHECK = (
    "(rettifica_raccolta_id IS NULL AND quantita > 0) OR "
    "(rettifica_raccolta_id IS NOT NULL AND "
    "(quantita <> 0 OR destinazione_prevista IS NOT NULL))"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_constraint(
        "ck_raccolte_ordinary_or_correction", "raccolte", schema=SCHEMA, type_="check",
    )
    op.create_check_constraint(
        "ck_raccolte_ordinary_or_correction", "raccolte", NEW_CHECK, schema=SCHEMA,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not context.is_offline_mode():
        annotated_zero = bind.execute(
            sa.text(
                "SELECT count(*) FROM tpo.raccolte WHERE rettifica_raccolta_id IS NOT NULL "
                "AND quantita = 0 AND destinazione_prevista IS NOT NULL"
            )
        ).scalar_one()
        if annotated_zero:
            raise RuntimeError(
                "cannot downgrade: RACCOLTA CORREZIONE annotation-only rows "
                "(quantita=0 with destinazione_prevista) exist and would violate "
                "the prior narrower check constraint"
            )
    op.drop_constraint(
        "ck_raccolte_ordinary_or_correction", "raccolte", schema=SCHEMA, type_="check",
    )
    op.create_check_constraint(
        "ck_raccolte_ordinary_or_correction", "raccolte", OLD_CHECK, schema=SCHEMA,
    )
