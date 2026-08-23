"""Commission explicit Production Planning Identity registrations."""

from __future__ import annotations

import sys

from scripts.commissioning.secret_boundary import load_postgresql_parameters

from src.tpo_core.application.identity import CommissionIdentityRegistration
from src.tpo_core.application.identity.production_planning import (
    PRODUCTION_PLANNING_SEQUENCE_TYPES,
)
from src.tpo_core.bootstrap import build_identity_registration_commissioner
from src.tpo_core.domain.identifiers import ActorId
from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings


ACTOR = ActorId("tpo.identity-commissioner")


def commission_production_planning_identity() -> tuple[str, ...]:
    parameters = load_postgresql_parameters()
    settings = PostgreSQLSettings.from_mapping(
        {
            "host": parameters["host"],
            "port": parameters["port"],
            "database": parameters["dbname"],
            "user": parameters["user"],
            "password": parameters["password"],
            "sslmode": parameters["sslmode"],
            "connect_timeout_seconds": parameters["connect_timeout"],
        }
    )
    service = build_identity_registration_commissioner(settings)
    commissioned = []
    for sequence_name, identifier_type in PRODUCTION_PLANNING_SEQUENCE_TYPES.items():
        result = service.commission(
            CommissionIdentityRegistration(
                sequence_name=sequence_name,
                permanent_id_type=identifier_type,
                prefix=identifier_type.prefix,
                actor=ACTOR,
            )
        )
        commissioned.append(result.command.sequence_name)
    return tuple(commissioned)


def main() -> int:
    try:
        names = commission_production_planning_identity()
    except Exception:
        print("PRODUCTION PLANNING IDENTITY COMMISSIONING FAILED", file=sys.stderr)
        return 1
    for name in names:
        print(f"IDENTITY REGISTRATION READY: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
