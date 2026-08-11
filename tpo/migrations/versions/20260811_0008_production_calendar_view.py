"""Create the complete Production Calendar read model.

Revision ID: 20260811_0008
Revises: 20260811_0007
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260811_0008"
down_revision: str | Sequence[str] | None = "20260811_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEW_SQL = """CREATE VIEW tpo.v_calendario_produzione AS
SELECT
    r.hydration_at AS event_at,
    (r.hydration_at AT TIME ZONE 'Atlantic/Canary')::date AS event_date,
    'IDRATAZIONE_PIANIFICATA'::text AS event_type,
    true AS planned,
    p.public_id AS piano_public_id,
    rev.public_id AS revision_public_id,
    r.public_id AS riga_piano_public_id,
    NULL::text AS semina_public_id,
    NULL::text AS raccolta_public_id,
    NULL::text AS consegna_public_id,
    r.stato::text AS source_state,
    r.varieta_id,
    r.cultivar_id,
    r.cultivar_uso_id,
    r.quantita_produttiva_autorizzata AS quantita,
    'SET'::tpo.unit_of_measure AS unita_misura,
    r.data_consegna,
    'tpo.righe_piano_semina.hydration_at'::text AS provenance
FROM tpo.righe_piano_semina AS r
JOIN tpo.piano_produzione_revisioni AS rev ON rev.id = r.piano_revisione_id
JOIN tpo.piani_produzione AS p ON p.id = rev.piano_produzione_id
WHERE r.hydration_at < r.sowing_at

UNION ALL

SELECT
    r.sowing_at AS event_at,
    (r.sowing_at AT TIME ZONE 'Atlantic/Canary')::date AS event_date,
    'SEMINA_PIANIFICATA'::text AS event_type,
    true AS planned,
    p.public_id AS piano_public_id,
    rev.public_id AS revision_public_id,
    r.public_id AS riga_piano_public_id,
    NULL::text AS semina_public_id,
    NULL::text AS raccolta_public_id,
    NULL::text AS consegna_public_id,
    r.stato::text AS source_state,
    r.varieta_id,
    r.cultivar_id,
    r.cultivar_uso_id,
    r.quantita_produttiva_autorizzata AS quantita,
    'SET'::tpo.unit_of_measure AS unita_misura,
    r.data_consegna,
    'tpo.righe_piano_semina.sowing_at'::text AS provenance
FROM tpo.righe_piano_semina AS r
JOIN tpo.piano_produzione_revisioni AS rev ON rev.id = r.piano_revisione_id
JOIN tpo.piani_produzione AS p ON p.id = rev.piano_produzione_id

UNION ALL

SELECT
    r.light_at AS event_at,
    (r.light_at AT TIME ZONE 'Atlantic/Canary')::date AS event_date,
    'LUCE_PIANIFICATA'::text AS event_type,
    true AS planned,
    p.public_id AS piano_public_id,
    rev.public_id AS revision_public_id,
    r.public_id AS riga_piano_public_id,
    NULL::text AS semina_public_id,
    NULL::text AS raccolta_public_id,
    NULL::text AS consegna_public_id,
    r.stato::text AS source_state,
    r.varieta_id,
    r.cultivar_id,
    r.cultivar_uso_id,
    r.quantita_produttiva_autorizzata AS quantita,
    'SET'::tpo.unit_of_measure AS unita_misura,
    r.data_consegna,
    'tpo.righe_piano_semina.light_at'::text AS provenance
FROM tpo.righe_piano_semina AS r
JOIN tpo.piano_produzione_revisioni AS rev ON rev.id = r.piano_revisione_id
JOIN tpo.piani_produzione AS p ON p.id = rev.piano_produzione_id

UNION ALL

SELECT
    r.harvest_target_at AS event_at,
    (r.harvest_target_at AT TIME ZONE 'Atlantic/Canary')::date AS event_date,
    'RACCOLTA_TARGET'::text AS event_type,
    true AS planned,
    p.public_id AS piano_public_id,
    rev.public_id AS revision_public_id,
    r.public_id AS riga_piano_public_id,
    NULL::text AS semina_public_id,
    NULL::text AS raccolta_public_id,
    NULL::text AS consegna_public_id,
    r.stato::text AS source_state,
    r.varieta_id,
    r.cultivar_id,
    r.cultivar_uso_id,
    r.quantita_produttiva_autorizzata AS quantita,
    'SET'::tpo.unit_of_measure AS unita_misura,
    r.data_consegna,
    'tpo.righe_piano_semina.harvest_target_at'::text AS provenance
FROM tpo.righe_piano_semina AS r
JOIN tpo.piano_produzione_revisioni AS rev ON rev.id = r.piano_revisione_id
JOIN tpo.piani_produzione AS p ON p.id = rev.piano_produzione_id

UNION ALL

SELECT
    s.data_avvio AS event_at,
    (s.data_avvio AT TIME ZONE 'Atlantic/Canary')::date AS event_date,
    'SEMINA_REALE'::text AS event_type,
    false AS planned,
    p.public_id AS piano_public_id,
    rev.public_id AS revision_public_id,
    r.public_id AS riga_piano_public_id,
    s.public_id AS semina_public_id,
    NULL::text AS raccolta_public_id,
    NULL::text AS consegna_public_id,
    s.stato::text AS source_state,
    s.varieta_id,
    s.cultivar_id,
    s.cultivar_uso_id,
    link.quantita_avviata AS quantita,
    link.unita_misura,
    r.data_consegna,
    'tpo.semine.data_avvio'::text AS provenance
FROM tpo.semine AS s
LEFT JOIN tpo.righe_piano_semina_semine AS link ON link.semina_id = s.id
LEFT JOIN tpo.righe_piano_semina AS r ON r.id = link.riga_piano_semina_id
LEFT JOIN tpo.piano_produzione_revisioni AS rev ON rev.id = r.piano_revisione_id
LEFT JOIN tpo.piani_produzione AS p ON p.id = rev.piano_produzione_id

UNION ALL

SELECT
    ra.data_raccolta AS event_at,
    (ra.data_raccolta AT TIME ZONE 'Atlantic/Canary')::date AS event_date,
    'RACCOLTA_REALE'::text AS event_type,
    false AS planned,
    p.public_id AS piano_public_id,
    rev.public_id AS revision_public_id,
    r.public_id AS riga_piano_public_id,
    s.public_id AS semina_public_id,
    ra.public_id AS raccolta_public_id,
    NULL::text AS consegna_public_id,
    NULL::text AS source_state,
    s.varieta_id,
    s.cultivar_id,
    s.cultivar_uso_id,
    ra.quantita,
    ra.unita_misura,
    r.data_consegna,
    'tpo.raccolte.data_raccolta'::text AS provenance
FROM tpo.raccolte AS ra
JOIN tpo.semine AS s ON s.id = ra.semina_id
LEFT JOIN tpo.righe_piano_semina_semine AS link ON link.semina_id = s.id
LEFT JOIN tpo.righe_piano_semina AS r ON r.id = link.riga_piano_semina_id
LEFT JOIN tpo.piano_produzione_revisioni AS rev ON rev.id = r.piano_revisione_id
LEFT JOIN tpo.piani_produzione AS p ON p.id = rev.piano_produzione_id

UNION ALL

SELECT
    c.data_effettiva AS event_at,
    (c.data_effettiva AT TIME ZONE 'Atlantic/Canary')::date AS event_date,
    'CONSEGNA_EFFETTIVA'::text AS event_type,
    false AS planned,
    NULL::text AS piano_public_id,
    NULL::text AS revision_public_id,
    NULL::text AS riga_piano_public_id,
    NULL::text AS semina_public_id,
    NULL::text AS raccolta_public_id,
    c.public_id AS consegna_public_id,
    c.stato::text AS source_state,
    NULL::bigint AS varieta_id,
    NULL::bigint AS cultivar_id,
    NULL::bigint AS cultivar_uso_id,
    NULL::numeric(20,6) AS quantita,
    NULL::tpo.unit_of_measure AS unita_misura,
    c.data_prevista AS data_consegna,
    'tpo.consegne.data_effettiva'::text AS provenance
FROM tpo.consegne AS c
WHERE c.stato = 'CONSEGNATA'
  AND c.data_effettiva IS NOT NULL"""


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(VIEW_SQL)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP VIEW tpo.v_calendario_produzione")
