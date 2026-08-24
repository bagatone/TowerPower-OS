"""Make replanning disposition validation record-shape safe.

Revision ID: 20260824_0018
Revises: 20260824_0017
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260824_0018"
down_revision: str | Sequence[str] | None = "20260824_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FIXED_FUNCTION = r"""
CREATE OR REPLACE FUNCTION tpo.fn_replanning_disposition_validate()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE set_id bigint; decision_id bigint; bad boolean;
BEGIN
  IF TG_TABLE_NAME = 'replanning_disposition_sets' THEN
    set_id := NEW.id;
  ELSIF TG_TABLE_NAME = 'replanning_disposition_decisions' THEN
    IF TG_OP = 'DELETE' THEN
      set_id := OLD.disposition_set_id;
    ELSE
      set_id := NEW.disposition_set_id;
    END IF;
  ELSIF TG_TABLE_NAME = 'replanning_disposition_replacements' THEN
    IF TG_OP = 'DELETE' THEN
      decision_id := OLD.disposition_decision_id;
    ELSE
      decision_id := NEW.disposition_decision_id;
    END IF;
    SELECT disposition_set_id INTO set_id
    FROM tpo.replanning_disposition_decisions WHERE id = decision_id;
  ELSE
    RAISE EXCEPTION 'unsupported replanning disposition trigger table: %', TG_TABLE_NAME;
  END IF;
  IF (SELECT state FROM tpo.replanning_disposition_sets WHERE id=set_id)='AUTHORIZED' THEN
    SELECT EXISTS (
      SELECT 1 FROM (
        SELECT position,row_number() OVER (ORDER BY a.public_id) AS expected
        FROM tpo.replanning_disposition_decisions d
        JOIN tpo.allocazioni a ON a.id=d.allocation_id
        WHERE d.disposition_set_id=set_id
      ) q WHERE position<>expected
    ) INTO bad;
    IF bad THEN
      RAISE EXCEPTION 'replanning disposition positions are not canonical and dense';
    END IF;
    SELECT EXISTS (
      SELECT 1 FROM tpo.replanning_disposition_decisions d
      LEFT JOIN tpo.replanning_disposition_replacements r
        ON r.disposition_decision_id=d.id
      WHERE d.disposition_set_id=set_id
        AND ((d.target_disposition='SOSTITUITA') <>
             (r.disposition_decision_id IS NOT NULL))
    ) INTO bad;
    IF bad THEN
      RAISE EXCEPTION 'replanning replacement cardinality mismatch';
    END IF;
  END IF;
  RETURN NULL;
END $$;
"""

HISTORICAL_FUNCTION = r"""
CREATE OR REPLACE FUNCTION tpo.fn_replanning_disposition_validate()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE set_id bigint; bad boolean;
BEGIN
  set_id := CASE WHEN TG_TABLE_NAME='replanning_disposition_sets' THEN NEW.id
                 WHEN TG_TABLE_NAME='replanning_disposition_decisions' THEN COALESCE(NEW.disposition_set_id,OLD.disposition_set_id)
                 ELSE (SELECT disposition_set_id FROM tpo.replanning_disposition_decisions
                       WHERE id=COALESCE(NEW.disposition_decision_id,OLD.disposition_decision_id)) END;
  IF (SELECT state FROM tpo.replanning_disposition_sets WHERE id=set_id)='AUTHORIZED' THEN
    SELECT EXISTS (
      SELECT 1 FROM (
        SELECT position,row_number() OVER (ORDER BY a.public_id) AS expected
        FROM tpo.replanning_disposition_decisions d JOIN tpo.allocazioni a ON a.id=d.allocation_id
        WHERE d.disposition_set_id=set_id
      ) q WHERE position<>expected
    ) INTO bad;
    IF bad THEN RAISE EXCEPTION 'replanning disposition positions are not canonical and dense'; END IF;
    SELECT EXISTS (
      SELECT 1 FROM tpo.replanning_disposition_decisions d
      LEFT JOIN tpo.replanning_disposition_replacements r ON r.disposition_decision_id=d.id
      WHERE d.disposition_set_id=set_id
        AND ((d.target_disposition='SOSTITUITA') <> (r.disposition_decision_id IS NOT NULL))
    ) INTO bad;
    IF bad THEN RAISE EXCEPTION 'replanning replacement cardinality mismatch'; END IF;
  END IF;
  RETURN NULL;
END $$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(FIXED_FUNCTION)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(HISTORICAL_FUNCTION)
