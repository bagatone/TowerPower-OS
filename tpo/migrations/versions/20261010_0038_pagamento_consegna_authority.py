"""PAGAMENTO_CONSEGNA Authority V1 (PAGAMENTO_CONSEGNA_AUTHORITY_FREEZE.md).

Revision ID: 20261010_0038
Revises: 20261003_0037

Fact append-only che dice se una CONSEGNA e' stata pagata, senza aspettare la
FATTURA. La CONSEGNA resta immutabile (tr_consegne_effective_immutable): il
"pagato" e' un Fact separato che la richiama. Lo stato (PAGATA / DA PAGARE) non
e' memorizzato: si deriva (un PAGAMENTO non annullato).

Pattern: INCASSO (FINANZE_AZIENDALI_AUTHORITY_FREEZE.md) con due semplificazioni
deliberate: l'idempotenza vive nella riga stessa (chiave univoca + hash del
payload, nessuna tabella di prenotazione) e l'annullamento e' un secondo Fact
(tipo ANNULLAMENTO) invece di una rettifica con importo.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261010_0038"
down_revision: str | Sequence[str] | None = "20261003_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"
METODO_PAGAMENTO = "'BONIFICO','CONTANTI','CARTA','BIZUM','ALTRO'"

TRIGGERS_SQL = r"""
CREATE FUNCTION tpo.protect_pagamento_consegna_authority()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  RAISE EXCEPTION 'Pagamento consegna physical fact authority is immutable';
END $$;
CREATE TRIGGER protect_pagamento_consegna_authority
BEFORE UPDATE OR DELETE ON tpo.pagamenti_consegna
FOR EACH ROW EXECUTE FUNCTION tpo.protect_pagamento_consegna_authority();

CREATE FUNCTION tpo.fn_pagamenti_consegna_coerente() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original tpo.pagamenti_consegna%ROWTYPE;
        stato_consegna text;
        attivi integer;
BEGIN
  IF NEW.tipo = 'PAGAMENTO' THEN
    SELECT stato::text INTO stato_consegna FROM tpo.consegne WHERE id = NEW.consegna_id;
    IF stato_consegna IS DISTINCT FROM 'CONSEGNATA' THEN
      RAISE EXCEPTION 'ct_pagamenti_consegna_coerente: consegna non CONSEGNATA';
    END IF;
    SELECT count(*) INTO attivi FROM tpo.pagamenti_consegna p
     WHERE p.consegna_id = NEW.consegna_id AND p.tipo = 'PAGAMENTO'
       AND NOT EXISTS (SELECT 1 FROM tpo.pagamenti_consegna a
                       WHERE a.annulla_pagamento_id = p.id);
    IF attivi > 1 THEN
      RAISE EXCEPTION 'ct_pagamenti_consegna_coerente: consegna gia'' pagata';
    END IF;
  ELSE
    SELECT * INTO original FROM tpo.pagamenti_consegna WHERE id = NEW.annulla_pagamento_id;
    IF NOT FOUND OR original.tipo <> 'PAGAMENTO' OR original.consegna_id <> NEW.consegna_id THEN
      RAISE EXCEPTION 'ct_pagamenti_consegna_coerente: annullamento incoerente';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
CREATE CONSTRAINT TRIGGER ct_pagamenti_consegna_coerente
AFTER INSERT ON tpo.pagamenti_consegna
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tpo.fn_pagamenti_consegna_coerente();
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "pagamenti_consegna",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("consegna_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("data_pagamento", sa.Date()),
        sa.Column("metodo", sa.Text()),
        sa.Column("importo", sa.Numeric(12, 2)),
        sa.Column("note", sa.Text()),
        sa.Column("storico", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("annulla_pagamento_id", sa.BigInteger()),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["consegna_id"], [f"{SCHEMA}.consegne.id"],
            name="fk_pagamenti_consegna_consegna", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["annulla_pagamento_id"], [f"{SCHEMA}.pagamenti_consegna.id"],
            name="fk_pagamenti_consegna_annulla", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("annulla_pagamento_id", name="uq_pagamenti_consegna_annulla"),
        sa.CheckConstraint("tipo IN ('PAGAMENTO','ANNULLAMENTO')", name="ck_pagamenti_consegna_tipo"),
        sa.CheckConstraint(
            "metodo IS NULL OR metodo IN (" + METODO_PAGAMENTO + ")",
            name="ck_pagamenti_consegna_metodo",
        ),
        sa.CheckConstraint(
            "importo IS NULL OR importo > 0", name="ck_pagamenti_consegna_importo",
        ),
        sa.CheckConstraint(
            "(tipo = 'PAGAMENTO' AND data_pagamento IS NOT NULL AND metodo IS NOT NULL "
            "AND annulla_pagamento_id IS NULL) OR "
            "(tipo = 'ANNULLAMENTO' AND annulla_pagamento_id IS NOT NULL "
            "AND data_pagamento IS NULL AND metodo IS NULL AND importo IS NULL "
            "AND storico = false)",
            name="ck_pagamenti_consegna_forma",
        ),
        sa.CheckConstraint("note IS NULL OR btrim(note) <> ''", name="ck_pagamenti_consegna_note"),
        sa.CheckConstraint(
            "btrim(idempotency_key) <> '' AND btrim(reason) <> '' "
            "AND btrim(correlation_id) <> '' AND btrim(created_by) <> ''",
            name="ck_pagamenti_consegna_testi",
        ),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_pagamenti_consegna_public_id_format", "pagamenti_consegna",
        "public_id ~ '^PGC-[0-9]{6,}$'", schema=SCHEMA,
    )
    op.create_index(
        "ix_pagamenti_consegna_consegna", "pagamenti_consegna", ["consegna_id"], schema=SCHEMA,
    )
    op.execute(sa.text(
        """INSERT INTO tpo.id_sequences
           (sequence_name,identifier_type,prefix,next_value,version,updated_at,updated_by)
           VALUES ('PAGAMENTO_CONSEGNA_ID','PagamentoConsegnaId','PGC',1,0,CURRENT_TIMESTAMP,
                   'migration-20261010-0038')"""
    ))
    op.execute(TRIGGERS_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    count = bind.execute(sa.text("SELECT count(*) FROM tpo.pagamenti_consegna")).scalar_one()
    if count:
        raise RuntimeError(
            "cannot downgrade: governed PAGAMENTO CONSEGNA authority history exists"
        )
    op.execute("""
DROP TRIGGER ct_pagamenti_consegna_coerente ON tpo.pagamenti_consegna;
DROP FUNCTION tpo.fn_pagamenti_consegna_coerente();
DROP TRIGGER protect_pagamento_consegna_authority ON tpo.pagamenti_consegna;
DROP FUNCTION tpo.protect_pagamento_consegna_authority();
""")
    op.execute(sa.text(
        "DELETE FROM tpo.id_sequences WHERE sequence_name='PAGAMENTO_CONSEGNA_ID' "
        "AND next_value=1"
    ))
    op.drop_index("ix_pagamenti_consegna_consegna", table_name="pagamenti_consegna", schema=SCHEMA)
    op.drop_table("pagamenti_consegna", schema=SCHEMA)
