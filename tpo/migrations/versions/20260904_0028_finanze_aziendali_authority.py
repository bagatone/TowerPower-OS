"""Finanze Aziendali Authority V1 — INCASSO + USCITA (FINANZE_AZIENDALI_AUTHORITY_FREEZE.md).

Revision ID: 20260904_0028
Revises: 20260903_0027
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260904_0028"
down_revision: str | Sequence[str] | None = "20260903_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

# Precedente strutturale diretto: RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md, già
# implementato in 20260830_0022_raccolta_authority.py e
# 20260903_0027_raccolta_correzione_authority.py. INCASSO e USCITA replicano lo
# stesso pattern in scala doppia (due registri Fact paralleli), con una sola
# deviazione deliberata: nessuna guardia sul saldo cumulativo dell'importo —
# l'owner ha esplicitamente rifiutato qualunque vincolo sull'importo
# (FINANZE_AZIENDALI_AUTHORITY_FREEZE.md §3, Owner Decision D3).
TRIGGERS_SQL = r"""
CREATE FUNCTION tpo.protect_incasso_authority()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  RAISE EXCEPTION 'Incasso physical fact authority is immutable';
END $$;
CREATE TRIGGER protect_incasso_authority
BEFORE UPDATE OR DELETE ON tpo.incassi
FOR EACH ROW EXECUTE FUNCTION tpo.protect_incasso_authority();

CREATE FUNCTION tpo.protect_uscita_authority()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  RAISE EXCEPTION 'Uscita physical fact authority is immutable';
END $$;
CREATE TRIGGER protect_uscita_authority
BEFORE UPDATE OR DELETE ON tpo.uscite
FOR EACH ROW EXECUTE FUNCTION tpo.protect_uscita_authority();

CREATE FUNCTION tpo.protect_incasso_recording_request()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.operation_scope=OLD.operation_scope
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.incasso_id IS NULL AND OLD.result_public_id IS NULL
     AND NEW.incasso_id IS NOT NULL AND NEW.result_public_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Incasso recording request authority is immutable';
END $$;
CREATE TRIGGER protect_incasso_recording_request
BEFORE UPDATE OR DELETE ON tpo.incasso_recording_requests
FOR EACH ROW EXECUTE FUNCTION tpo.protect_incasso_recording_request();

CREATE FUNCTION tpo.protect_uscita_recording_request()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.operation_scope=OLD.operation_scope
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.uscita_id IS NULL AND OLD.result_public_id IS NULL
     AND NEW.uscita_id IS NOT NULL AND NEW.result_public_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Uscita recording request authority is immutable';
END $$;
CREATE TRIGGER protect_uscita_recording_request
BEFORE UPDATE OR DELETE ON tpo.uscita_recording_requests
FOR EACH ROW EXECUTE FUNCTION tpo.protect_uscita_recording_request();

CREATE FUNCTION tpo.protect_incasso_correzione_request()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.operation_scope=OLD.operation_scope
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.incasso_id IS NULL AND OLD.result_public_id IS NULL
     AND NEW.incasso_id IS NOT NULL AND NEW.result_public_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Incasso correzione request authority is immutable';
END $$;
CREATE TRIGGER protect_incasso_correzione_request
BEFORE UPDATE OR DELETE ON tpo.incasso_correzione_requests
FOR EACH ROW EXECUTE FUNCTION tpo.protect_incasso_correzione_request();

CREATE FUNCTION tpo.protect_uscita_correzione_request()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.operation_scope=OLD.operation_scope
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.uscita_id IS NULL AND OLD.result_public_id IS NULL
     AND NEW.uscita_id IS NOT NULL AND NEW.result_public_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Uscita correzione request authority is immutable';
END $$;
CREATE TRIGGER protect_uscita_correzione_request
BEFORE UPDATE OR DELETE ON tpo.uscita_correzione_requests
FOR EACH ROW EXECUTE FUNCTION tpo.protect_uscita_correzione_request();

CREATE FUNCTION tpo.fn_incassi_rettifica_coerente() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original tpo.incassi%ROWTYPE;
BEGIN
  IF NEW.rettifica_incasso_id IS NULL THEN RETURN NEW; END IF;
  IF NEW.id = NEW.rettifica_incasso_id THEN
    RAISE EXCEPTION 'ct_incassi_rettifica_coerente self reference';
  END IF;
  SELECT * INTO original FROM tpo.incassi WHERE id = NEW.rettifica_incasso_id;
  IF NOT FOUND OR original.rettifica_incasso_id IS NOT NULL
     OR original.fattura_numero <> NEW.fattura_numero THEN
    RAISE EXCEPTION 'ct_incassi_rettifica_coerente violated';
  END IF;
  RETURN NEW;
END;
$$;
CREATE CONSTRAINT TRIGGER ct_incassi_rettifica_coerente
AFTER INSERT ON tpo.incassi
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tpo.fn_incassi_rettifica_coerente();

CREATE FUNCTION tpo.fn_uscite_rettifica_coerente() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original tpo.uscite%ROWTYPE;
BEGIN
  IF NEW.rettifica_uscita_id IS NULL THEN RETURN NEW; END IF;
  IF NEW.id = NEW.rettifica_uscita_id THEN
    RAISE EXCEPTION 'ct_uscite_rettifica_coerente self reference';
  END IF;
  SELECT * INTO original FROM tpo.uscite WHERE id = NEW.rettifica_uscita_id;
  IF NOT FOUND OR original.rettifica_uscita_id IS NOT NULL THEN
    RAISE EXCEPTION 'ct_uscite_rettifica_coerente violated';
  END IF;
  RETURN NEW;
END;
$$;
CREATE CONSTRAINT TRIGGER ct_uscite_rettifica_coerente
AFTER INSERT ON tpo.uscite
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tpo.fn_uscite_rettifica_coerente();
"""

METODO_PAGAMENTO = "'BONIFICO','CONTANTI','CARTA','BIZUM','ALTRO'"
CATEGORIA_USCITA = (
    "'SEMENTI','ATTREZZATURA','AFFITTO','UTENZE','STIPENDI','TRASPORTO','ALTRO'"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "incassi",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("fattura_numero", sa.Text(), nullable=False),
        sa.Column("importo", sa.Numeric(12, 2), nullable=False),
        sa.Column("data_incasso", sa.Date(), nullable=False),
        sa.Column("metodo", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("rettifica_incasso_id", sa.BigInteger()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fattura_numero"], [f"{SCHEMA}.fatture.numero_fattura"],
            name="fk_incassi_fattura", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rettifica_incasso_id"], [f"{SCHEMA}.incassi.id"],
            name="fk_incassi_rettifica", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "public_id", name="uq_incassi_id_public_id"),
        sa.CheckConstraint(
            "metodo IN (" + METODO_PAGAMENTO + ")", name="ck_incassi_metodo",
        ),
        sa.CheckConstraint("note IS NULL OR btrim(note) <> ''", name="ck_incassi_note_not_blank"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_incassi_created_by_not_blank"),
        sa.CheckConstraint(
            "(rettifica_incasso_id IS NULL AND importo > 0) OR "
            "(rettifica_incasso_id IS NOT NULL AND importo <> 0)",
            name="ck_incassi_ordinary_or_correction",
        ),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_incassi_public_id_format", "incassi", "public_id ~ '^INC-[0-9]{6,}$'",
        schema=SCHEMA,
    )
    op.create_index("ix_incassi_fattura_numero", "incassi", ["fattura_numero"], schema=SCHEMA)
    op.create_index("ix_incassi_data_incasso", "incassi", ["data_incasso"], schema=SCHEMA)
    op.create_index(
        "ix_incassi_rettifica_incasso_id", "incassi", ["rettifica_incasso_id"], schema=SCHEMA,
    )

    op.create_table(
        "uscite",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("importo", sa.Numeric(12, 2), nullable=False),
        sa.Column("data_uscita", sa.Date(), nullable=False),
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column("beneficiario", sa.Text(), nullable=False),
        sa.Column("metodo", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("rettifica_uscita_id", sa.BigInteger()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["rettifica_uscita_id"], [f"{SCHEMA}.uscite.id"],
            name="fk_uscite_rettifica", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "public_id", name="uq_uscite_id_public_id"),
        sa.CheckConstraint(
            "categoria IN (" + CATEGORIA_USCITA + ")", name="ck_uscite_categoria",
        ),
        sa.CheckConstraint(
            "btrim(beneficiario) <> ''", name="ck_uscite_beneficiario_not_blank",
        ),
        sa.CheckConstraint(
            "metodo IN (" + METODO_PAGAMENTO + ")", name="ck_uscite_metodo",
        ),
        sa.CheckConstraint("note IS NULL OR btrim(note) <> ''", name="ck_uscite_note_not_blank"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_uscite_created_by_not_blank"),
        sa.CheckConstraint(
            "(rettifica_uscita_id IS NULL AND importo > 0) OR "
            "(rettifica_uscita_id IS NOT NULL AND importo <> 0)",
            name="ck_uscite_ordinary_or_correction",
        ),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_uscite_public_id_format", "uscite", "public_id ~ '^USC-[0-9]{6,}$'",
        schema=SCHEMA,
    )
    op.create_index("ix_uscite_data_uscita", "uscite", ["data_uscita"], schema=SCHEMA)
    op.create_index("ix_uscite_categoria", "uscite", ["categoria"], schema=SCHEMA)
    op.create_index(
        "ix_uscite_rettifica_uscita_id", "uscite", ["rettifica_uscita_id"], schema=SCHEMA,
    )

    # Nomi letterali (non f-string) per i vincoli soggetti a verifica di
    # governance sul testo sorgente della migrazione (frozen guard names).
    RECORDING_REQUEST_KEY_NAMES = {
        "incasso": "uq_incasso_recording_request_key",
        "uscita": "uq_uscita_recording_request_key",
    }
    for label, id_column, table in (
        ("incasso", "incasso_id", "incassi"), ("uscita", "uscita_id", "uscite"),
    ):
        op.create_table(
            f"{label}_recording_requests",
            sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
            sa.Column("operation_scope", sa.Text(), nullable=False),
            sa.Column("idempotency_key", sa.Text(), nullable=False),
            sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
            sa.Column(id_column, sa.BigInteger()),
            sa.Column("result_public_id", sa.Text()),
            sa.Column("outcome", sa.Text(), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(
                [id_column, "result_public_id"],
                [f"{SCHEMA}.{table}.id", f"{SCHEMA}.{table}.public_id"],
                onupdate="RESTRICT", ondelete="RESTRICT",
                name=f"fk_{label}_recording_authoritative_result",
                deferrable=True, initially="DEFERRED",
            ),
            sa.UniqueConstraint(
                "operation_scope", "idempotency_key",
                name=RECORDING_REQUEST_KEY_NAMES[label],
            ),
            sa.UniqueConstraint(id_column, name=f"uq_{label}_recording_{label}"),
            sa.UniqueConstraint("result_public_id", name=f"uq_{label}_recording_result"),
            sa.CheckConstraint(
                f"operation_scope='{label.upper()}_RECORDING_V1'",
                name=f"ck_{label}_recording_scope",
            ),
            sa.CheckConstraint("btrim(idempotency_key)<>''", name=f"ck_{label}_recording_key"),
            sa.CheckConstraint(
                "canonical_payload_hash ~ '^[0-9a-f]{64}$'", name=f"ck_{label}_recording_hash",
            ),
            sa.CheckConstraint(
                f"(outcome='RESERVED' AND {id_column} IS NULL AND result_public_id IS NULL) OR "
                f"(outcome='COMMITTED' AND {id_column} IS NOT NULL "
                "AND result_public_id IS NOT NULL)",
                name=f"ck_{label}_recording_outcome",
            ),
            sa.CheckConstraint("btrim(created_by)<>''", name=f"ck_{label}_recording_actor"),
            schema=SCHEMA,
        )
        op.create_index(
            f"ix_{label}_recording_result", f"{label}_recording_requests",
            ["result_public_id"], schema=SCHEMA,
        )

        op.create_table(
            f"{label}_correzione_requests",
            sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
            sa.Column("operation_scope", sa.Text(), nullable=False),
            sa.Column("idempotency_key", sa.Text(), nullable=False),
            sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
            sa.Column(id_column, sa.BigInteger()),
            sa.Column("result_public_id", sa.Text()),
            sa.Column("outcome", sa.Text(), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(
                [id_column, "result_public_id"],
                [f"{SCHEMA}.{table}.id", f"{SCHEMA}.{table}.public_id"],
                onupdate="RESTRICT", ondelete="RESTRICT",
                name=f"fk_{label}_correzione_authoritative_result",
                deferrable=True, initially="DEFERRED",
            ),
            sa.UniqueConstraint(
                "operation_scope", "idempotency_key",
                name=f"uq_{label}_correzione_request_key",
            ),
            sa.UniqueConstraint(id_column, name=f"uq_{label}_correzione_{label}"),
            sa.UniqueConstraint("result_public_id", name=f"uq_{label}_correzione_result"),
            sa.CheckConstraint(
                f"operation_scope='{label.upper()}_CORREZIONE_V1'",
                name=f"ck_{label}_correzione_scope",
            ),
            sa.CheckConstraint("btrim(idempotency_key)<>''", name=f"ck_{label}_correzione_key"),
            sa.CheckConstraint(
                "canonical_payload_hash ~ '^[0-9a-f]{64}$'", name=f"ck_{label}_correzione_hash",
            ),
            sa.CheckConstraint(
                f"(outcome='RESERVED' AND {id_column} IS NULL AND result_public_id IS NULL) OR "
                f"(outcome='COMMITTED' AND {id_column} IS NOT NULL "
                "AND result_public_id IS NOT NULL)",
                name=f"ck_{label}_correzione_outcome",
            ),
            sa.CheckConstraint("btrim(created_by)<>''", name=f"ck_{label}_correzione_actor"),
            schema=SCHEMA,
        )
        op.create_index(
            f"ix_{label}_correzione_result", f"{label}_correzione_requests",
            ["result_public_id"], schema=SCHEMA,
        )

    op.execute(sa.text(
        """INSERT INTO tpo.id_sequences
           (sequence_name,identifier_type,prefix,next_value,version,updated_at,updated_by)
           VALUES ('INCASSO_ID','IncassoId','INC',1,0,CURRENT_TIMESTAMP,
                   'migration-20260904-0028')"""
    ))
    op.execute(sa.text(
        """INSERT INTO tpo.id_sequences
           (sequence_name,identifier_type,prefix,next_value,version,updated_at,updated_by)
           VALUES ('USCITA_ID','UscitaId','USC',1,0,CURRENT_TIMESTAMP,
                   'migration-20260904-0028')"""
    ))

    op.execute(TRIGGERS_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not context.is_offline_mode():
        counts = bind.execute(sa.text(
            "SELECT (SELECT count(*) FROM tpo.incassi) + "
            "(SELECT count(*) FROM tpo.uscite) + "
            "(SELECT count(*) FROM tpo.incasso_recording_requests) + "
            "(SELECT count(*) FROM tpo.uscita_recording_requests) + "
            "(SELECT count(*) FROM tpo.incasso_correzione_requests) + "
            "(SELECT count(*) FROM tpo.uscita_correzione_requests)"
        )).scalar_one()
        if counts:
            raise RuntimeError(
                "cannot downgrade: governed FINANZE AZIENDALI authority history exists"
            )

    op.execute("""
DROP TRIGGER ct_uscite_rettifica_coerente ON tpo.uscite;
DROP FUNCTION tpo.fn_uscite_rettifica_coerente();
DROP TRIGGER ct_incassi_rettifica_coerente ON tpo.incassi;
DROP FUNCTION tpo.fn_incassi_rettifica_coerente();
DROP TRIGGER protect_uscita_correzione_request ON tpo.uscita_correzione_requests;
DROP FUNCTION tpo.protect_uscita_correzione_request();
DROP TRIGGER protect_incasso_correzione_request ON tpo.incasso_correzione_requests;
DROP FUNCTION tpo.protect_incasso_correzione_request();
DROP TRIGGER protect_uscita_recording_request ON tpo.uscita_recording_requests;
DROP FUNCTION tpo.protect_uscita_recording_request();
DROP TRIGGER protect_incasso_recording_request ON tpo.incasso_recording_requests;
DROP FUNCTION tpo.protect_incasso_recording_request();
DROP TRIGGER protect_uscita_authority ON tpo.uscite;
DROP FUNCTION tpo.protect_uscita_authority();
DROP TRIGGER protect_incasso_authority ON tpo.incassi;
DROP FUNCTION tpo.protect_incasso_authority();
""")

    op.execute(sa.text(
        "DELETE FROM tpo.id_sequences WHERE sequence_name='USCITA_ID' "
        "AND identifier_type='UscitaId' AND prefix='USC' AND next_value=1 AND version=0"
    ))
    op.execute(sa.text(
        "DELETE FROM tpo.id_sequences WHERE sequence_name='INCASSO_ID' "
        "AND identifier_type='IncassoId' AND prefix='INC' AND next_value=1 AND version=0"
    ))

    for label in ("uscita", "incasso"):
        op.drop_index(
            f"ix_{label}_correzione_result", table_name=f"{label}_correzione_requests",
            schema=SCHEMA,
        )
        op.drop_table(f"{label}_correzione_requests", schema=SCHEMA)
        op.drop_index(
            f"ix_{label}_recording_result", table_name=f"{label}_recording_requests",
            schema=SCHEMA,
        )
        op.drop_table(f"{label}_recording_requests", schema=SCHEMA)

    op.drop_index("ix_uscite_rettifica_uscita_id", table_name="uscite", schema=SCHEMA)
    op.drop_index("ix_uscite_categoria", table_name="uscite", schema=SCHEMA)
    op.drop_index("ix_uscite_data_uscita", table_name="uscite", schema=SCHEMA)
    op.drop_table("uscite", schema=SCHEMA)

    op.drop_index("ix_incassi_rettifica_incasso_id", table_name="incassi", schema=SCHEMA)
    op.drop_index("ix_incassi_data_incasso", table_name="incassi", schema=SCHEMA)
    op.drop_index("ix_incassi_fattura_numero", table_name="incassi", schema=SCHEMA)
    op.drop_table("incassi", schema=SCHEMA)
