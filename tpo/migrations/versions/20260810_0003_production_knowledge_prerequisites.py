"""Create production-knowledge and seed-material prerequisites.

Revision ID: 20260810_0003
Revises: 20260806_0002
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260810_0003"
down_revision: str | Sequence[str] | None = "20260806_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"

varieta_state = postgresql.ENUM(
    "ATTIVA", "IN_SPERIMENTAZIONE", "SOSPESA", "DISMESSA",
    name="varieta_state", schema=SCHEMA, create_type=False,
)
unit_of_measure = postgresql.ENUM(
    "SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA, create_type=False
)
protocollo_tipo = postgresql.ENUM(
    "STANDARD", "SPERIMENTALE", name="protocollo_tipo", schema=SCHEMA, create_type=False
)
semente_raccomandazione = postgresql.ENUM(
    "RACCOMANDATA", "UTILIZZABILE", "SCONSIGLIATA",
    name="semente_raccomandazione", schema=SCHEMA, create_type=False,
)
NEW_ENUMS = (protocollo_tipo, semente_raccomandazione)


def _audit_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
    )


def _audit_checks(prefix: str) -> tuple[sa.CheckConstraint, ...]:
    return (
        sa.CheckConstraint("btrim(created_by) <> ''", name=f"ck_{prefix}_created_by_not_blank"),
        sa.CheckConstraint("btrim(updated_by) <> ''", name=f"ck_{prefix}_updated_by_not_blank"),
        sa.CheckConstraint("updated_at >= created_at", name=f"ck_{prefix}_updated_not_before_created"),
        sa.CheckConstraint("version >= 0", name=f"ck_{prefix}_version_nonnegative"),
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum in NEW_ENUMS:
            enum.create(bind, checkfirst=True)
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "cultivar",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("varieta_id", sa.BigInteger(), nullable=False),
        sa.Column("denominazione", sa.Text(), nullable=False),
        sa.Column("stato", varieta_state, nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(["varieta_id"], [f"{SCHEMA}.varieta.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.CheckConstraint("btrim(denominazione) <> ''", name="ck_cultivar_denominazione_not_blank"),
        *_audit_checks("cultivar"),
        schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_index("uq_cultivar_varieta_denominazione_normalized", "cultivar", ["varieta_id", sa.text("lower(btrim(denominazione))")], unique=True, schema=SCHEMA)
    op.create_index("ix_cultivar_varieta_id", "cultivar", ["varieta_id"], schema=SCHEMA)
    op.create_index("ix_cultivar_varieta_stato", "cultivar", ["varieta_id", "stato"], schema=SCHEMA)

    op.create_table(
        "usi_produttivi",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("codice", sa.Text(), nullable=False, unique=True),
        sa.Column("denominazione", sa.Text(), nullable=False),
        sa.Column("attivo", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_audit_columns(),
        sa.CheckConstraint("btrim(codice) <> ''", name="ck_usi_produttivi_codice_not_blank"),
        sa.CheckConstraint("btrim(denominazione) <> ''", name="ck_usi_produttivi_denominazione_not_blank"),
        *_audit_checks("usi_produttivi"),
        schema=SCHEMA,
    )
    op.create_index("ix_usi_produttivi_attivo", "usi_produttivi", ["attivo"], schema=SCHEMA)

    op.create_table(
        "cultivar_usi",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("cultivar_id", sa.BigInteger(), nullable=False),
        sa.Column("uso_produttivo_id", sa.BigInteger(), nullable=False),
        sa.Column("stato_validazione", sa.Text(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(["cultivar_id"], [f"{SCHEMA}.cultivar.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uso_produttivo_id"], [f"{SCHEMA}.usi_produttivi.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.UniqueConstraint("cultivar_id", "uso_produttivo_id", name="uq_cultivar_usi_cultivar_uso"),
        sa.CheckConstraint("btrim(stato_validazione) <> ''", name="ck_cultivar_usi_stato_validazione_not_blank"),
        *_audit_checks("cultivar_usi"),
        schema=SCHEMA,
    )
    op.create_index("ix_cultivar_usi_cultivar_id", "cultivar_usi", ["cultivar_id"], schema=SCHEMA)
    op.create_index("ix_cultivar_usi_uso_produttivo_id", "cultivar_usi", ["uso_produttivo_id"], schema=SCHEMA)
    op.create_index("ix_cultivar_usi_stato_validazione", "cultivar_usi", ["stato_validazione"], schema=SCHEMA)

    op.create_table(
        "protocolli",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("cultivar_uso_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", protocollo_tipo, nullable=False),
        sa.Column("denominazione", sa.Text(), nullable=False),
        sa.Column("attivo", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_audit_columns(),
        sa.ForeignKeyConstraint(["cultivar_uso_id"], [f"{SCHEMA}.cultivar_usi.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.CheckConstraint("btrim(denominazione) <> ''", name="ck_protocolli_denominazione_not_blank"),
        *_audit_checks("protocolli"),
        schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_index("uq_protocolli_cultivar_uso_tipo_denominazione_normalized", "protocolli", ["cultivar_uso_id", "tipo", sa.text("lower(btrim(denominazione))")], unique=True, schema=SCHEMA)
    op.create_index("uq_protocolli_standard_attivo", "protocolli", ["cultivar_uso_id"], unique=True, schema=SCHEMA, postgresql_where=sa.text("tipo = 'STANDARD' AND attivo"), sqlite_where=sa.text("tipo = 'STANDARD' AND attivo = 1"))
    op.create_index("ix_protocolli_cultivar_uso_id", "protocolli", ["cultivar_uso_id"], schema=SCHEMA)
    op.create_index("ix_protocolli_cultivar_uso_tipo_attivo", "protocolli", ["cultivar_uso_id", "tipo", "attivo"], schema=SCHEMA)

    op.create_table(
        "protocollo_versioni",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("protocollo_id", sa.BigInteger(), nullable=False),
        sa.Column("numero_versione", sa.Integer(), nullable=False),
        sa.Column("valida_dal", sa.Date(), nullable=False),
        sa.Column("valida_al", sa.Date()),
        sa.Column("versione_precedente_id", sa.BigInteger()),
        sa.Column("contenuto", sa.Text(), nullable=False),
        sa.Column("motivazione", sa.Text(), nullable=False),
        sa.Column("evidenze", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["protocollo_id"], [f"{SCHEMA}.protocolli.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["versione_precedente_id"], [f"{SCHEMA}.protocollo_versioni.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.UniqueConstraint("protocollo_id", "numero_versione", name="uq_protocollo_versioni_protocollo_numero"),
        sa.UniqueConstraint("versione_precedente_id", name="uq_protocollo_versioni_precedente"),
        sa.CheckConstraint("numero_versione > 0", name="ck_protocollo_versioni_numero_positive"),
        sa.CheckConstraint("valida_al IS NULL OR valida_al >= valida_dal", name="ck_protocollo_versioni_validita"),
        sa.CheckConstraint("btrim(contenuto) <> ''", name="ck_protocollo_versioni_contenuto_not_blank"),
        sa.CheckConstraint("btrim(motivazione) <> ''", name="ck_protocollo_versioni_motivazione_not_blank"),
        sa.CheckConstraint("evidenze IS NULL OR btrim(evidenze) <> ''", name="ck_protocollo_versioni_evidenze_not_blank"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_protocollo_versioni_created_by_not_blank"),
        schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE tpo.protocollo_versioni ADD CONSTRAINT ex_protocollo_versioni_validita EXCLUDE USING gist (protocollo_id WITH =, daterange(valida_dal, valida_al, '[)') WITH &&)")
    op.create_index("ix_protocollo_versioni_protocollo_id", "protocollo_versioni", ["protocollo_id"], schema=SCHEMA)
    op.create_index("ix_protocollo_versioni_valida_dal", "protocollo_versioni", ["valida_dal"], schema=SCHEMA)
    op.create_index("ix_protocollo_versioni_versione_precedente_id", "protocollo_versioni", ["versione_precedente_id"], schema=SCHEMA)

    op.create_table(
        "sementi",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("fornitore", sa.Text(), nullable=False),
        sa.Column("referenza_commerciale", sa.Text(), nullable=False),
        sa.Column("marca", sa.Text()), sa.Column("formato", sa.Text()),
        sa.Column("trattamento", sa.Text()), sa.Column("certificazioni", sa.Text()),
        sa.Column("attiva", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_audit_columns(),
        sa.CheckConstraint("btrim(fornitore) <> ''", name="ck_sementi_fornitore_not_blank"),
        sa.CheckConstraint("btrim(referenza_commerciale) <> ''", name="ck_sementi_referenza_not_blank"),
        sa.CheckConstraint("marca IS NULL OR btrim(marca) <> ''", name="ck_sementi_marca_not_blank"),
        sa.CheckConstraint("formato IS NULL OR btrim(formato) <> ''", name="ck_sementi_formato_not_blank"),
        sa.CheckConstraint("trattamento IS NULL OR btrim(trattamento) <> ''", name="ck_sementi_trattamento_not_blank"),
        sa.CheckConstraint("certificazioni IS NULL OR btrim(certificazioni) <> ''", name="ck_sementi_certificazioni_not_blank"),
        *_audit_checks("sementi"), schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_index("uq_sementi_fornitore_referenza_normalized", "sementi", [sa.text("lower(btrim(fornitore))"), sa.text("lower(btrim(referenza_commerciale))")], unique=True, schema=SCHEMA)
    op.create_index("ix_sementi_fornitore", "sementi", ["fornitore"], schema=SCHEMA)
    op.create_index("ix_sementi_attiva", "sementi", ["attiva"], schema=SCHEMA)

    op.create_table(
        "semente_impieghi",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("semente_id", sa.BigInteger(), nullable=False),
        sa.Column("cultivar_uso_id", sa.BigInteger(), nullable=False),
        sa.Column("raccomandazione", semente_raccomandazione, nullable=False),
        sa.Column("rating", sa.Numeric(5, 2)),
        sa.Column("motivazione", sa.Text()),
        sa.Column("ultima_revisione", sa.Date(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(["semente_id"], [f"{SCHEMA}.sementi.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cultivar_uso_id"], [f"{SCHEMA}.cultivar_usi.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.UniqueConstraint("semente_id", "cultivar_uso_id", name="uq_semente_impieghi_semente_cultivar_uso"),
        sa.CheckConstraint("rating IS NULL OR rating BETWEEN 0 AND 100", name="ck_semente_impieghi_rating_range"),
        sa.CheckConstraint("motivazione IS NULL OR btrim(motivazione) <> ''", name="ck_semente_impieghi_motivazione_not_blank"),
        *_audit_checks("semente_impieghi"), schema=SCHEMA,
    )
    op.create_index("ix_semente_impieghi_semente_id", "semente_impieghi", ["semente_id"], schema=SCHEMA)
    op.create_index("ix_semente_impieghi_cultivar_uso_id", "semente_impieghi", ["cultivar_uso_id"], schema=SCHEMA)
    op.create_index("ix_semente_impieghi_uso_raccomandazione", "semente_impieghi", ["cultivar_uso_id", "raccomandazione"], schema=SCHEMA)

    op.create_table(
        "lotti_seme",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("semente_id", sa.BigInteger(), nullable=False),
        sa.Column("numero_lotto_produttore", sa.Text(), nullable=False),
        sa.Column("data_ricezione", sa.Date(), nullable=False),
        sa.Column("data_scadenza", sa.Date()),
        sa.Column("quantita_iniziale", sa.Numeric(20, 6), nullable=False),
        sa.Column("quantita_residua", sa.Numeric(20, 6), nullable=False),
        sa.Column("unita_misura", unit_of_measure, nullable=False),
        sa.Column("anomalia", sa.Text()),
        *_audit_columns(),
        sa.ForeignKeyConstraint(["semente_id"], [f"{SCHEMA}.sementi.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.UniqueConstraint("semente_id", "numero_lotto_produttore", name="uq_lotti_seme_semente_numero_lotto"),
        sa.CheckConstraint("data_scadenza IS NULL OR data_scadenza >= data_ricezione", name="ck_lotti_seme_scadenza"),
        sa.CheckConstraint("quantita_iniziale > 0", name="ck_lotti_seme_quantita_iniziale_positive"),
        sa.CheckConstraint("quantita_residua >= 0 AND quantita_residua <= quantita_iniziale", name="ck_lotti_seme_quantita_residua"),
        sa.CheckConstraint("btrim(numero_lotto_produttore) <> ''", name="ck_lotti_seme_numero_not_blank"),
        sa.CheckConstraint("anomalia IS NULL OR btrim(anomalia) <> ''", name="ck_lotti_seme_anomalia_not_blank"),
        *_audit_checks("lotti_seme"), schema=SCHEMA,
    )
    op.create_index("ix_lotti_seme_semente_id", "lotti_seme", ["semente_id"], schema=SCHEMA)
    op.create_index("ix_lotti_seme_data_scadenza", "lotti_seme", ["data_scadenza"], schema=SCHEMA)
    op.create_index("ix_lotti_seme_semente_data_ricezione", "lotti_seme", ["semente_id", "data_ricezione"], schema=SCHEMA)


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("lotti_seme", "semente_impieghi", "sementi", "protocollo_versioni", "protocolli", "cultivar_usi", "usi_produttivi", "cultivar"):
        op.drop_table(table, schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        for enum in reversed(NEW_ENUMS):
            enum.drop(bind, checkfirst=True)
