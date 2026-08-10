"""Seed operativo iniziale delle sequenze Identity autorizzate."""

from __future__ import annotations

import sys

import psycopg

from secret_boundary import load_postgresql_parameters


EXPECTED_ROWS = {
    ("ORDINE_ID", "OrdineId", "ORD", 1, 0, "tpo.identity"),
    ("RUN_ID", "RunId", "RUN", 1, 0, "tpo.identity"),
}


def seed_identity() -> None:
    parameters = load_postgresql_parameters()

    with psycopg.connect(**parameters) as connection:
        with connection.transaction():
            connection.execute(
                "LOCK TABLE tpo.id_sequences IN SHARE ROW EXCLUSIVE MODE"
            )
            connection.execute("LOCK TABLE tpo.runs, tpo.ordini IN SHARE MODE")

            if connection.execute(
                "SELECT EXISTS (SELECT 1 FROM tpo.id_sequences)"
            ).fetchone()[0]:
                raise RuntimeError("identity sequences already exist")

            if connection.execute(
                "SELECT EXISTS "
                "(SELECT 1 FROM tpo.runs WHERE public_id LIKE 'RUN-%')"
            ).fetchone()[0]:
                raise RuntimeError("historical RUN identifiers exist")

            if connection.execute(
                "SELECT EXISTS "
                "(SELECT 1 FROM tpo.ordini WHERE public_id LIKE 'ORD-%')"
            ).fetchone()[0]:
                raise RuntimeError("historical ORD identifiers exist")

            connection.execute(
                """
                INSERT INTO tpo.id_sequences (
                    sequence_name,
                    identifier_type,
                    prefix,
                    next_value,
                    version,
                    updated_at,
                    updated_by
                )
                VALUES
                    ('RUN_ID', 'RunId', 'RUN', 1, 0,
                     CURRENT_TIMESTAMP, 'tpo.identity'),
                    ('ORDINE_ID', 'OrdineId', 'ORD', 1, 0,
                     CURRENT_TIMESTAMP, 'tpo.identity')
                """
            )

            rows = connection.execute(
                """
                SELECT sequence_name,
                       identifier_type,
                       prefix,
                       next_value,
                       version,
                       updated_by,
                       updated_at IS NOT NULL
                FROM tpo.id_sequences
                ORDER BY sequence_name
                """
            ).fetchall()

            actual_rows = {tuple(row[:6]) for row in rows}
            timestamps_valid = all(row[6] for row in rows)
            if (
                len(rows) != 2
                or actual_rows != EXPECTED_ROWS
                or not timestamps_valid
            ):
                raise RuntimeError("identity seed postcondition failed")


def main() -> int:
    try:
        seed_identity()
    except Exception:
        print("IDENTITY SEED FAILED", file=sys.stderr)
        return 1

    print("IDENTITY SEED APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
