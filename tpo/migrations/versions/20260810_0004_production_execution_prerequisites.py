"""Create production-execution and stock prerequisites.

Revision ID: 20260810_0004
Revises: 20260810_0003
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260810_0004"
down_revision: str | Sequence[str] | None = "20260810_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"

unit_of_measure = postgresql.ENUM("SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA, create_type=False)
semina_state = postgresql.ENUM("AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA", "CHIUSA", name="semina_state", schema=SCHEMA, create_type=False)
semina_esito = postgresql.ENUM("RACCOLTA_COMPLETA", "RACCOLTA_PARZIALE_CON_SCARTO", "SCARTO_TOTALE", "INTERRUZIONE", name="semina_esito", schema=SCHEMA, create_type=False)
consegna_state = postgresql.ENUM("PROGRAMMATA", "IN_PREPARAZIONE", "CONSEGNATA", "ANNULLATA", name="consegna_state", schema=SCHEMA, create_type=False)
movimento_type = postgresql.ENUM("CARICO", "SCARICO", "RETTIFICA", name="movimento_type", schema=SCHEMA, create_type=False)
movimento_direction = postgresql.ENUM("POSITIVO", "NEGATIVO", name="movimento_direction", schema=SCHEMA, create_type=False)
NEW_ENUMS = (semina_state, semina_esito, consegna_state, movimento_type, movimento_direction)

MOVIMENTO_ORIGIN_REFERENCE_CHECK = (
    "(origine_tipo = 'RACCOLTA' AND raccolta_id IS NOT NULL AND consegna_id IS NULL) OR "
    "(origine_tipo = 'CONSEGNA' AND consegna_id IS NOT NULL AND raccolta_id IS NULL) OR "
    "(origine_tipo NOT IN ('RACCOLTA', 'CONSEGNA') AND raccolta_id IS NULL AND consegna_id IS NULL)"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum in NEW_ENUMS:
            enum.create(bind, checkfirst=True)

    op.create_table(
        "semine",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("varieta_id", sa.BigInteger(), nullable=False),
        sa.Column("cultivar_id", sa.BigInteger(), nullable=False),
        sa.Column("cultivar_uso_id", sa.BigInteger(), nullable=False),
        sa.Column("lotto_seme_id", sa.BigInteger(), nullable=False),
        sa.Column("protocollo_versione_id", sa.BigInteger(), nullable=False),
        sa.Column("stato", semina_state, nullable=False),
        sa.Column("quantita_seme", sa.Numeric(20, 6), nullable=False),
        sa.Column("unita_misura", unit_of_measure, nullable=False),
        sa.Column("data_avvio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("causa_origine", sa.Text(), nullable=False),
        sa.Column("esito_finale", semina_esito),
        sa.Column("cultivar_snapshot", sa.Text(), nullable=False),
        sa.Column("uso_produttivo_snapshot", sa.Text(), nullable=False),
        sa.Column("lotto_seme_snapshot", sa.Text(), nullable=False),
        sa.Column("protocollo_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["varieta_id"], [f"{SCHEMA}.varieta.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cultivar_id"], [f"{SCHEMA}.cultivar.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cultivar_uso_id"], [f"{SCHEMA}.cultivar_usi.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lotto_seme_id"], [f"{SCHEMA}.lotti_seme.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["protocollo_versione_id"], [f"{SCHEMA}.protocollo_versioni.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.CheckConstraint("quantita_seme > 0", name="ck_semine_quantita_positive"),
        sa.CheckConstraint("unita_misura = 'GRAM'", name="ck_semine_uom_gram"),
        sa.CheckConstraint("btrim(causa_origine) <> ''", name="ck_semine_causa_not_blank"),
        sa.CheckConstraint("(stato = 'CHIUSA' AND esito_finale IS NOT NULL) OR (stato <> 'CHIUSA' AND esito_finale IS NULL)", name="ck_semine_esito"),
        sa.CheckConstraint("btrim(cultivar_snapshot) <> '' AND btrim(uso_produttivo_snapshot) <> '' AND btrim(lotto_seme_snapshot) <> '' AND btrim(protocollo_snapshot) <> ''", name="ck_semine_snapshots_not_blank"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_semine_created_by_not_blank"),
        schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_check_constraint("ck_semine_public_id_format", "semine", "public_id ~ '^SEM-[0-9]{6,}$'", schema=SCHEMA)
    for column in ("varieta_id", "cultivar_id", "cultivar_uso_id", "lotto_seme_id", "protocollo_versione_id"):
        op.create_index(f"ix_semine_{column}", "semine", [column], schema=SCHEMA)
    op.create_index("ix_semine_stato_data_avvio", "semine", ["stato", "data_avvio"], schema=SCHEMA)
    op.create_index("ix_semine_causa_origine", "semine", ["causa_origine"], schema=SCHEMA)

    op.create_table(
        "raccolte",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("semina_id", sa.BigInteger(), nullable=False),
        sa.Column("data_raccolta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantita", sa.Numeric(20, 6), nullable=False),
        sa.Column("unita_misura", unit_of_measure, nullable=False),
        sa.Column("operatore", sa.Text()), sa.Column("destinazione_prevista", sa.Text()), sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["semina_id"], [f"{SCHEMA}.semine.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.CheckConstraint("quantita > 0", name="ck_raccolte_quantita_positive"),
        sa.CheckConstraint("unita_misura = 'SET'", name="ck_raccolte_uom_set"),
        sa.CheckConstraint("operatore IS NULL OR btrim(operatore) <> ''", name="ck_raccolte_operatore_not_blank"),
        sa.CheckConstraint("destinazione_prevista IS NULL OR btrim(destinazione_prevista) <> ''", name="ck_raccolte_destinazione_not_blank"),
        sa.CheckConstraint("note IS NULL OR btrim(note) <> ''", name="ck_raccolte_note_not_blank"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_raccolte_created_by_not_blank"), schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_check_constraint("ck_raccolte_public_id_format", "raccolte", "public_id ~ '^RAC-[0-9]{6,}$'", schema=SCHEMA)
    op.create_index("ix_raccolte_semina_id", "raccolte", ["semina_id"], schema=SCHEMA)
    op.create_index("ix_raccolte_semina_data", "raccolte", ["semina_id", "data_raccolta"], schema=SCHEMA)
    op.create_index("ix_raccolte_data_raccolta", "raccolte", ["data_raccolta"], schema=SCHEMA)

    op.create_table(
        "consegne",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("cliente_id", sa.BigInteger(), nullable=False),
        sa.Column("stato", consegna_state, nullable=False),
        sa.Column("data_prevista", sa.Date(), nullable=False),
        sa.Column("data_effettiva", sa.DateTime(timezone=True)),
        sa.Column("motivazione", sa.Text()), sa.Column("operatore", sa.Text()), sa.Column("destinazione_fisica", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["cliente_id"], [f"{SCHEMA}.clienti.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.CheckConstraint("(stato = 'CONSEGNATA' AND data_effettiva IS NOT NULL) OR (stato <> 'CONSEGNATA' AND data_effettiva IS NULL)", name="ck_consegne_data_effettiva"),
        sa.CheckConstraint("motivazione IS NULL OR btrim(motivazione) <> ''", name="ck_consegne_motivazione_not_blank"),
        sa.CheckConstraint("operatore IS NULL OR btrim(operatore) <> ''", name="ck_consegne_operatore_not_blank"),
        sa.CheckConstraint("destinazione_fisica IS NULL OR btrim(destinazione_fisica) <> ''", name="ck_consegne_destinazione_not_blank"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_consegne_created_by_not_blank"), schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_check_constraint("ck_consegne_public_id_format", "consegne", "public_id ~ '^CON-[0-9]{6,}$'", schema=SCHEMA)
    op.create_index("ix_consegne_cliente_id", "consegne", ["cliente_id"], schema=SCHEMA)
    op.create_index("ix_consegne_stato_data_prevista", "consegne", ["stato", "data_prevista"], schema=SCHEMA)
    op.create_index("ix_consegne_data_effettiva", "consegne", ["data_effettiva"], schema=SCHEMA)

    stock_foreign_keys = [
        sa.ForeignKeyConstraint(["varieta_id"], [f"{SCHEMA}.varieta.id"], onupdate="RESTRICT", ondelete="RESTRICT")
    ]
    if bind.dialect.name != "postgresql":
        stock_foreign_keys.append(
            sa.ForeignKeyConstraint(
                ["ultimo_movimento_id"],
                [f"{SCHEMA}.movimenti_magazzino.id"],
                name="fk_stock_ultimo_movimento_id",
                onupdate="RESTRICT",
                ondelete="RESTRICT",
            )
        )
    op.create_table(
        "stock",
        sa.Column("varieta_id", sa.BigInteger(), primary_key=True),
        sa.Column("disponibile", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("unita_misura", unit_of_measure, nullable=False),
        sa.Column("ultimo_movimento_id", sa.BigInteger()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        *stock_foreign_keys,
        sa.UniqueConstraint("varieta_id", "unita_misura", name="uq_stock_varieta_unita"),
        sa.CheckConstraint("disponibile >= 0", name="ck_stock_disponibile_nonnegative"),
        sa.CheckConstraint("version >= 0", name="ck_stock_version_nonnegative"), schema=SCHEMA,
    )
    op.create_index("ix_stock_updated_at", "stock", ["updated_at"], schema=SCHEMA)

    op.create_table(
        "movimenti_magazzino",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("varieta_id", sa.BigInteger(), nullable=False),
        sa.Column("unita_misura", unit_of_measure, nullable=False),
        sa.Column("tipo", movimento_type, nullable=False),
        sa.Column("direzione", movimento_direction, nullable=False),
        sa.Column("quantita", sa.Numeric(20, 6), nullable=False),
        sa.Column("data_movimento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("origine_tipo", sa.Text(), nullable=False),
        sa.Column("origine_riferimento", sa.Text()),
        sa.Column("raccolta_id", sa.BigInteger()), sa.Column("consegna_id", sa.BigInteger()), sa.Column("run_id", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["varieta_id", "unita_misura"], [f"{SCHEMA}.stock.varieta_id", f"{SCHEMA}.stock.unita_misura"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raccolta_id"], [f"{SCHEMA}.raccolte.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["consegna_id"], [f"{SCHEMA}.consegne.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], [f"{SCHEMA}.runs.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.CheckConstraint("quantita > 0", name="ck_movimenti_magazzino_quantita_positive"),
        sa.CheckConstraint("btrim(motivo) <> ''", name="ck_movimenti_magazzino_motivo_not_blank"),
        sa.CheckConstraint("btrim(origine_tipo) <> ''", name="ck_movimenti_magazzino_origine_tipo_not_blank"),
        sa.CheckConstraint("origine_riferimento IS NULL OR btrim(origine_riferimento) <> ''", name="ck_movimenti_magazzino_origine_riferimento_not_blank"),
        sa.CheckConstraint(
            MOVIMENTO_ORIGIN_REFERENCE_CHECK,
            name="ck_movimenti_magazzino_origine_references",
        ),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_movimenti_magazzino_created_by_not_blank"), schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_check_constraint("ck_movimenti_magazzino_public_id_format", "movimenti_magazzino", "public_id ~ '^MOV-[0-9]{6,}$'", schema=SCHEMA)
    op.create_index("ix_movimenti_magazzino_varieta_data", "movimenti_magazzino", ["varieta_id", "data_movimento"], schema=SCHEMA)
    op.create_index("ix_movimenti_magazzino_tipo", "movimenti_magazzino", ["tipo"], schema=SCHEMA)
    op.create_index("ix_movimenti_magazzino_origine", "movimenti_magazzino", ["origine_tipo", "origine_riferimento"], schema=SCHEMA)
    for column in ("raccolta_id", "consegna_id", "run_id"):
        op.create_index(f"ix_movimenti_magazzino_{column}", "movimenti_magazzino", [column], schema=SCHEMA)

    if bind.dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_stock_ultimo_movimento_id", "stock", "movimenti_magazzino",
            ["ultimo_movimento_id"], ["id"], source_schema=SCHEMA,
            referent_schema=SCHEMA, onupdate="RESTRICT", ondelete="RESTRICT",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("fk_stock_ultimo_movimento_id", "stock", schema=SCHEMA, type_="foreignkey")
    for table in ("movimenti_magazzino", "stock", "consegne", "raccolte", "semine"):
        op.drop_table(table, schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        for enum in reversed(NEW_ENUMS):
            enum.drop(bind, checkfirst=True)
