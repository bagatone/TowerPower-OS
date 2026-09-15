"""Crea il protocollo di coltivazione reale per Amaranto (VAR-000010),
mai commissionato finora (nessuna riga cultivar/cultivar_uso/protocollo/
protocollo_versione esisteva). Nessun comando CLI wired per questo
boundary (application/agronomic_commissioning esiste ma main.py non lo
espone -- gap noto) -- lo eseguiamo chiamando direttamente
l'application+infrastructure layer reale, stessa validazione di dominio
che userebbe una CLI, senza SQL a mano.

Dati agronomici forniti da Matteo/Giulia in chat il 15/9/2026: nessuna
idratazione, 4gg germinazione, 10gg luce, 10g seme per SET (1 SET = 10g,
confermato). Orario semina/raccolta, resa attesa, granularita' produttiva,
harvest lead e buffer presi identici ai 6 protocolli reali gia' esistenti
(tutti coincidenti su questi valori: farm standard operativo, non
agronomia specifica di varieta').
valida_dal=2026-08-01 (stesso bootstrap date degli altri 6 protocolli)
necessario perche' la semina Amaranto reale da registrare e' del 7/9/2026,
precedente a oggi.
"""
import sys
from pathlib import Path
from datetime import date, time
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.tpo_core.application.agronomic_commissioning.models import CommissionAgronomicProtocolCommand
from src.tpo_core.application.agronomic_commissioning.service import AgronomicProtocolCommissioningService
from src.tpo_core.domain.identifiers import ActorId, ProtocolloVersioneId, VarietaId
from src.tpo_core.infrastructure.clock import SystemClock
from src.tpo_core.infrastructure.postgresql.agronomic_commissioning import PostgreSQLAgronomicProtocolCommissioningWriter
from src.tpo_core.infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings

sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters  # noqa: E402

_params = load_postgresql_parameters()
settings = PostgreSQLSettings.from_mapping({
    "host": _params["host"],
    "port": _params["port"],
    "database": _params["dbname"],
    "user": _params["user"],
    "password": _params["password"],
    "sslmode": _params["sslmode"],
    "connect_timeout_seconds": _params["connect_timeout"],
})
service = AgronomicProtocolCommissioningService(
    writer=PostgreSQLAgronomicProtocolCommissioningWriter(PostgreSQLConnectionFactory(settings)),
    clock=SystemClock(),
)

command = CommissionAgronomicProtocolCommand(
    variety_id=VarietaId("VAR-000010"),
    variety_name="Amaranto",
    cultivar_name="Amaranto",
    productive_use_code="MICROGREEN",
    productive_use_name="Microgreens",
    protocol_name="Tower Power standard Amaranto",
    protocol_version_id=ProtocolloVersioneId("PV-000007"),
    version=1,
    valid_from=date(2026, 8, 1),
    valid_to=None,
    hydration_hours=Decimal("0"),
    planned_sowing_time=time(6, 0),
    target_harvest_time=time(6, 0),
    germination_days=4,
    light_growth_days=10,
    seed_grams_per_set=Decimal("10"),
    expected_yield=Decimal("1"),
    production_granularity=Decimal("0.5"),
    harvest_min_lead_days=1,
    harvest_max_lead_days=1,
    temporal_buffer_minutes=0,
    content="hydration_hours=0; germination_days=4; light_growth_days=10; seed_grams_per_set=10",
    motivation="Initial Tower Power real agronomic protocol commissioning for Production Planning V1.",
    evidence=None,
    provenance="OWNER_AUTHORIZED_REAL_GROWING_PROTOCOL_2026-09",
    actor=ActorId("tpo.owner"),  # stesso actor usato nel bootstrap originale di usi_produttivi (MICROGREEN)
    reason=("Creazione protocollo di coltivazione reale per Amaranto (mai commissionato), "
            "dati forniti da Matteo/Giulia in chat il 15/9/2026. Necessario per sbloccare "
            "il commissioning SEMINA reale gia' pendente (amaranto piantato 7/9)."),
    correlation_id="PROTOCOLLO-AMARANTO-2026-09-15",
)

result = service.commission(command)
print("STATUS: OK")
print(f"PROTOCOL_VERSION: {result.command.protocol_version_id.value}")
print(f"INSERTED: {result.inserted_entities}")
print(f"APPROVED_AT: {result.approved_at}")
