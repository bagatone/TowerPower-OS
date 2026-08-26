"""Semina Traceability Code Authority V1.

Revision ID: 20260826_0021
Revises: 20260825_0020
"""
from collections.abc import Sequence
from alembic import context, op
import sqlalchemy as sa

revision: str = "20260826_0021"
down_revision: str | Sequence[str] | None = "20260825_0020"
branch_labels = None
depends_on = None
SCHEMA = "tpo"


def upgrade() -> None:
    bind = op.get_bind()
    if (not context.is_offline_mode()
            and bind.execute(sa.text("SELECT count(*) FROM tpo.semine")).scalar_one()):
        raise RuntimeError(
            "forward-only cut-over blocked: existing SEMINE require a separately frozen migration"
        )
    variety_check = ("codice_tracciabilita ~ '^[A-Z]{3}$'" if bind.dialect.name == "postgresql"
                     else "length(codice_tracciabilita)=3 AND codice_tracciabilita NOT GLOB '*[^A-Z]*'")
    semina_check = ("codice_tracciabilita ~ '^[A-Z]{3}-[0-9]{4}-[A-Z]$'"
                    if bind.dialect.name == "postgresql" else
                    "length(codice_tracciabilita)=10 AND codice_tracciabilita GLOB '[A-Z][A-Z][A-Z]-[0-9][0-9][0-9][0-9]-[A-Z]'")
    with op.batch_alter_table("varieta", schema=SCHEMA) as batch:
        batch.add_column(sa.Column("codice_tracciabilita", sa.Text(), nullable=True))
        batch.create_unique_constraint("uq_varieta_codice_tracciabilita", ["codice_tracciabilita"])
        batch.create_check_constraint(
            "ck_varieta_codice_tracciabilita",
            f"codice_tracciabilita IS NULL OR ({variety_check})",
        )
    with op.batch_alter_table("semine", schema=SCHEMA) as batch:
        batch.add_column(sa.Column("codice_tracciabilita", sa.Text(), nullable=False))
        batch.create_unique_constraint("uq_semine_codice_tracciabilita", ["codice_tracciabilita"])
        batch.create_check_constraint("ck_semine_codice_tracciabilita", semina_check)
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
        CREATE FUNCTION tpo.protect_varieta_traceability_code()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF OLD.codice_tracciabilita IS NOT NULL
             AND NEW.codice_tracciabilita IS DISTINCT FROM OLD.codice_tracciabilita THEN
            RAISE EXCEPTION 'VARIETA traceability code is immutable once commissioned';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER protect_varieta_traceability_code
        BEFORE UPDATE ON tpo.varieta FOR EACH ROW
        EXECUTE FUNCTION tpo.protect_varieta_traceability_code();

        CREATE OR REPLACE FUNCTION tpo.protect_semina_constitutive_authority()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'SEMINA constitutive authority is immutable';
          END IF;
          IF NEW.public_id IS DISTINCT FROM OLD.public_id
             OR NEW.codice_tracciabilita IS DISTINCT FROM OLD.codice_tracciabilita
             OR NEW.varieta_id IS DISTINCT FROM OLD.varieta_id
             OR NEW.cultivar_id IS DISTINCT FROM OLD.cultivar_id
             OR NEW.cultivar_uso_id IS DISTINCT FROM OLD.cultivar_uso_id
             OR NEW.lotto_seme_id IS DISTINCT FROM OLD.lotto_seme_id
             OR NEW.protocollo_versione_id IS DISTINCT FROM OLD.protocollo_versione_id
             OR NEW.quantita_seme IS DISTINCT FROM OLD.quantita_seme
             OR NEW.unita_misura IS DISTINCT FROM OLD.unita_misura
             OR NEW.data_avvio IS DISTINCT FROM OLD.data_avvio
             OR NEW.causa_origine IS DISTINCT FROM OLD.causa_origine
             OR NEW.cultivar_snapshot IS DISTINCT FROM OLD.cultivar_snapshot
             OR NEW.uso_produttivo_snapshot IS DISTINCT FROM OLD.uso_produttivo_snapshot
             OR NEW.lotto_seme_snapshot IS DISTINCT FROM OLD.lotto_seme_snapshot
             OR NEW.protocollo_snapshot IS DISTINCT FROM OLD.protocollo_snapshot THEN
            RAISE EXCEPTION 'SEMINA constitutive authority is immutable';
          END IF;
          RETURN NEW;
        END $$;
        DROP TRIGGER protect_semina_constitutive_authority ON tpo.semine;
        CREATE TRIGGER protect_semina_constitutive_authority
        BEFORE UPDATE OR DELETE ON tpo.semine FOR EACH ROW
        EXECUTE FUNCTION tpo.protect_semina_constitutive_authority();
        """))


def downgrade() -> None:
    bind = op.get_bind()
    if (not context.is_offline_mode()
            and bind.execute(sa.text("SELECT count(*) FROM tpo.semine")).scalar_one()):
        raise RuntimeError("cannot downgrade: traceable SEMINE exist")
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
        DROP TRIGGER protect_varieta_traceability_code ON tpo.varieta;
        DROP FUNCTION tpo.protect_varieta_traceability_code();
        CREATE OR REPLACE FUNCTION tpo.protect_semina_constitutive_authority()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.public_id IS DISTINCT FROM OLD.public_id
             OR NEW.varieta_id IS DISTINCT FROM OLD.varieta_id
             OR NEW.cultivar_id IS DISTINCT FROM OLD.cultivar_id
             OR NEW.cultivar_uso_id IS DISTINCT FROM OLD.cultivar_uso_id
             OR NEW.lotto_seme_id IS DISTINCT FROM OLD.lotto_seme_id
             OR NEW.protocollo_versione_id IS DISTINCT FROM OLD.protocollo_versione_id
             OR NEW.quantita_seme IS DISTINCT FROM OLD.quantita_seme
             OR NEW.unita_misura IS DISTINCT FROM OLD.unita_misura
             OR NEW.data_avvio IS DISTINCT FROM OLD.data_avvio
             OR NEW.causa_origine IS DISTINCT FROM OLD.causa_origine
             OR NEW.cultivar_snapshot IS DISTINCT FROM OLD.cultivar_snapshot
             OR NEW.uso_produttivo_snapshot IS DISTINCT FROM OLD.uso_produttivo_snapshot
             OR NEW.lotto_seme_snapshot IS DISTINCT FROM OLD.lotto_seme_snapshot
             OR NEW.protocollo_snapshot IS DISTINCT FROM OLD.protocollo_snapshot THEN
            RAISE EXCEPTION 'SEMINA constitutive authority is immutable';
          END IF;
          RETURN NEW;
        END $$;
        DROP TRIGGER protect_semina_constitutive_authority ON tpo.semine;
        CREATE TRIGGER protect_semina_constitutive_authority
        BEFORE UPDATE ON tpo.semine FOR EACH ROW
        EXECUTE FUNCTION tpo.protect_semina_constitutive_authority();
        """))
    with op.batch_alter_table("semine", schema=SCHEMA) as batch:
        batch.drop_constraint("ck_semine_codice_tracciabilita", type_="check")
        batch.drop_constraint("uq_semine_codice_tracciabilita", type_="unique")
        batch.drop_column("codice_tracciabilita")
    with op.batch_alter_table("varieta", schema=SCHEMA) as batch:
        batch.drop_constraint("ck_varieta_codice_tracciabilita", type_="check")
        batch.drop_constraint("uq_varieta_codice_tracciabilita", type_="unique")
        batch.drop_column("codice_tracciabilita")
