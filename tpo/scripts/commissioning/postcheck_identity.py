"""Postcheck read-only del commissioning Identity."""

from __future__ import annotations

import psycopg

from secret_boundary import load_postgresql_parameters


EXPECTED_ROWS = {
    ("ORDINE_ID", "OrdineId", "ORD", 1, 0, "tpo.identity"),
    ("RUN_ID", "RunId", "RUN", 1, 0, "tpo.identity"),
}


def identity_postcheck() -> bool:
    parameters = load_postgresql_parameters()

    with psycopg.connect(**parameters) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")

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
            counts = connection.execute(
                """
                SELECT (SELECT count(*) FROM tpo.runs),
                       (SELECT count(*) FROM tpo.ordini)
                """
            ).fetchone()

    actual_rows = {tuple(row[:6]) for row in rows}
    timestamps_valid = all(row[6] for row in rows)
    return (
        len(rows) == 2
        and actual_rows == EXPECTED_ROWS
        and timestamps_valid
        and counts == (0, 0)
    )


def main() -> int:
    try:
        passed = identity_postcheck()
    except Exception:
        passed = False

    if passed:
        print("IDENTITY POSTCHECK: PASS")
        return 0

    print("IDENTITY POSTCHECK: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
