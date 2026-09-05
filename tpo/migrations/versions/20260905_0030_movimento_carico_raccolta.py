"""Movimento Carico Raccolta Authority V1 (MOVIMENTO_CARICO_AUTHORITY_FREEZE.md).

Revision ID: 20260905_0030
Revises: 20260905_0029

Pubblicazione governata di un carico di magazzino (MOVIMENTO tipo CARICO)
originato da una RACCOLTA reale, con incremento dello STOCK della VARIETA
corrispondente. Riserva già esplicitamente prevista da
RACCOLTA_AUTHORITY_FREEZE.md Sezione 11 ("la pubblicazione Raccolta ->
Movimento e' una futura authority boundary") e dallo schema esistente:
tpo.movimenti_magazzino ha gia' la colonna raccolta_id e il CHECK di origine
ammette gia' esplicitamente origine_tipo='RACCOLTA'. L'unica modifica additiva
a una tabella esistente e' lo stesso precedente gia' stabilito per RACCOLTA
(20260830_0022_raccolta_authority.py): una UNIQUE (id, public_id) su
movimenti_magazzino, necessaria perche' la FK composita della nuova tabella di
idempotenza referenzi (id, public_id) insieme (Postgres richiede un vincolo
UNIQUE/PK che copra esattamente l'insieme di colonne referenziato da una FK
composita; id da solo e public_id da solo non bastano). Nessuna colonna
aggiunta/rimossa/alterata su movimenti_magazzino/stock/raccolte.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260905_0030"
down_revision: str | Sequence[str] | None = "20260905_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

# Precedente strutturale diretto: tpo.raccolta_correzione_requests
# (migrations/versions/20260903_0027_raccolta_correzione_authority.py) per la
# forma della tabella di reservation/idempotenza e per il trigger di
# protezione. A differenza di quella tabella, qui la FK punta a
# tpo.movimenti_magazzino (il risultato committed e' un nuovo MOVIMENTO, non
# una nuova RACCOLTA): ogni richiesta committed produce esattamente un
# movimento, quindi movimento_id e' UNIQUE 1:1 con la request, mentre
# raccolta_id (l'origine, non il risultato) resta solo un campo del payload
# applicativo gia' coperto da canonical_payload_hash, non una colonna di
# questa tabella.
TRIGGERS_SQL = r"""
CREATE FUNCTION tpo.protect_movimento_carico_request() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.operation_scope=OLD.operation_scope
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.movimento_id IS NULL AND OLD.result_public_id IS NULL
     AND NEW.movimento_id IS NOT NULL AND NEW.result_public_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Movimento carico request authority is immutable';
END $$;
CREATE TRIGGER protect_movimento_carico_request
BEFORE UPDATE OR DELETE ON tpo.movimento_carico_requests
FOR EACH ROW EXECUTE FUNCTION tpo.protect_movimento_carico_request();
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Stesso precedente di raccolte (20260830_0022_raccolta_authority.py): la FK
    # composita sotto richiede un vincolo UNIQUE che copra esattamente
    # (id, public_id), che movimenti_magazzino non ha ancora (id e' PRIMARY KEY,
    # public_id ha una propria UNIQUE separata, ma non insieme).
    with op.batch_alter_table("movimenti_magazzino", schema=SCHEMA) as batch:
        batch.create_unique_constraint(
            "uq_movimenti_magazzino_id_public_id", ["id", "public_id"]
        )

    op.create_table(
        "movimento_carico_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("movimento_id", sa.BigInteger()),
        sa.Column("result_public_id", sa.Text()),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["movimento_id", "result_public_id"],
            ["tpo.movimenti_magazzino.id", "tpo.movimenti_magazzino.public_id"],
            onupdate="RESTRICT", ondelete="RESTRICT",
            name="fk_movimento_carico_authoritative_result",
            deferrable=True, initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "operation_scope", "idempotency_key",
            name="uq_movimento_carico_request_key",
        ),
        sa.UniqueConstraint("movimento_id", name="uq_movimento_carico_movimento"),
        sa.UniqueConstraint("result_public_id", name="uq_movimento_carico_result"),
        sa.CheckConstraint(
            "operation_scope='MOVIMENTO_CARICO_RACCOLTA_V1'",
            name="ck_movimento_carico_scope",
        ),
        sa.CheckConstraint("btrim(idempotency_key)<>''", name="ck_movimento_carico_key"),
        sa.CheckConstraint(
            "canonical_payload_hash ~ '^[0-9a-f]{64}$'", name="ck_movimento_carico_hash",
        ),
        sa.CheckConstraint(
            "(outcome='RESERVED' AND movimento_id IS NULL AND result_public_id IS NULL) OR "
            "(outcome='COMMITTED' AND movimento_id IS NOT NULL AND result_public_id IS NOT NULL)",
            name="ck_movimento_carico_outcome",
        ),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_movimento_carico_actor"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_movimento_carico_result", "movimento_carico_requests",
        ["result_public_id"], schema=SCHEMA,
    )

    op.execute(TRIGGERS_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not context.is_offline_mode():
        requests = bind.execute(
            sa.text("SELECT count(*) FROM tpo.movimento_carico_requests")
        ).scalar_one()
        if requests:
            raise RuntimeError(
                "cannot downgrade: governed MOVIMENTO CARICO authority history exists"
            )

    op.execute("""
DROP TRIGGER protect_movimento_carico_request ON tpo.movimento_carico_requests;
DROP FUNCTION tpo.protect_movimento_carico_request();
""")

    op.drop_index(
        "ix_movimento_carico_result", table_name="movimento_carico_requests", schema=SCHEMA,
    )
    op.drop_table("movimento_carico_requests", schema=SCHEMA)

    with op.batch_alter_table("movimenti_magazzino", schema=SCHEMA) as batch:
        batch.drop_constraint("uq_movimenti_magazzino_id_public_id", type_="unique")
