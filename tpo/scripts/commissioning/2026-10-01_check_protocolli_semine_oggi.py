"""Diagnostica di sola lettura: per le 7 varieta' delle semine di oggi
(Cilantro, Mizuna, Rabano, Rucola, Basilico, Amaranto, Pak Choi), mostra
il protocollo STANDARD attivo con la sua versione APPROVATA corrente
(grammi_seme_per_set e tempistiche) e i lotti di seme disponibili con
stock residuo -- per confrontare con quanto detto a voce da Matteo prima
di commissionare qualunque semina reale."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "commissioning"))
from secret_boundary import load_postgresql_parameters
import psycopg

VARIETA = ["Cilantro", "Mizuna", "Rábano", "Rucola", "Basilico", "Amaranto", "Pak Choi"]

parameters = load_postgresql_parameters()
conn = psycopg.connect(
    host=parameters["host"], port=parameters["port"], dbname=parameters["dbname"],
    user=parameters["user"], password=parameters["password"], sslmode=parameters["sslmode"],
    connect_timeout=parameters["connect_timeout"],
)
try:
    with conn.cursor() as cur:
        for nome in VARIETA:
            print(f"=== {nome} ===")
            cur.execute(
                """SELECT v.public_id, v.denominazione, cu.cultivar_id, c.denominazione,
                          cu.id, up.denominazione
                   FROM tpo.varieta v
                   JOIN tpo.cultivar c ON c.varieta_id = v.id
                   JOIN tpo.cultivar_usi cu ON cu.cultivar_id = c.id
                   JOIN tpo.usi_produttivi up ON up.id = cu.uso_produttivo_id
                   WHERE v.denominazione = %s""",
                (nome,),
            )
            cultivar_usi = cur.fetchall()
            if not cultivar_usi:
                print("    NESSUN cultivar/uso produttivo trovato per questa varieta'")
                continue
            for (v_pid, v_denom, cultivar_id, cultivar_denom, cultivar_uso_id, uso_denom) in cultivar_usi:
                print(f"    varieta {v_pid} / cultivar '{cultivar_denom}' / uso '{uso_denom}' (cultivar_uso_id={cultivar_uso_id})")
                cur.execute(
                    """SELECT p.id, p.denominazione, p.tipo, p.attivo
                       FROM tpo.protocolli p WHERE p.cultivar_uso_id = %s""",
                    (cultivar_uso_id,),
                )
                for (proto_id, proto_denom, tipo, attivo) in cur.fetchall():
                    print(f"        protocollo '{proto_denom}' tipo={tipo} attivo={attivo} (id={proto_id})")
                    cur.execute(
                        """SELECT pv.public_id, pv.numero_versione, pv.stato_approvazione,
                                  pv.grammi_seme_per_set, pv.idratazione_ore,
                                  pv.germinazione_giorni, pv.crescita_luce_giorni,
                                  pv.valida_dal, pv.valida_al
                           FROM tpo.protocollo_versioni pv
                           WHERE pv.protocollo_id = %s ORDER BY pv.numero_versione""",
                        (proto_id,),
                    )
                    for row in cur.fetchall():
                        (pv_pid, num, stato, grammi, idrat, germ, luce, v_dal, v_al) = row
                        print(
                            f"            {pv_pid} v{num} stato={stato} "
                            f"grammi_seme_per_set={grammi} idratazione_ore={idrat} "
                            f"germinazione_giorni={germ} crescita_luce_giorni={luce} "
                            f"valida_dal={v_dal} valida_al={v_al}"
                        )
                cur.execute(
                    """SELECT si.id, s.id, s.fornitore, s.referenza_commerciale,
                              si.raccomandazione, si.rating
                       FROM tpo.semente_impieghi si
                       JOIN tpo.sementi s ON s.id = si.semente_id
                       WHERE si.cultivar_uso_id = %s
                       ORDER BY si.raccomandazione, si.rating DESC NULLS LAST""",
                    (cultivar_uso_id,),
                )
                impieghi = cur.fetchall()
                for (si_id, s_internal_id, fornitore, referenza, racc, rating) in impieghi:
                    cur.execute(
                        """SELECT public_id, numero_lotto_produttore, quantita_residua,
                                  unita_misura, data_scadenza, anomalia
                           FROM tpo.lotti_seme WHERE semente_id = (
                               SELECT semente_id FROM tpo.semente_impieghi WHERE id = %s
                           ) ORDER BY data_ricezione DESC""",
                        (si_id,),
                    )
                    lotti = cur.fetchall()
                    print(f"        semente (id={s_internal_id}) {fornitore}/{referenza} raccomandazione={racc} rating={rating}")
                    for (lse_pid, numero_lotto, residuo, unita, scadenza, anomalia) in lotti:
                        flag = f" ANOMALIA: {anomalia}" if anomalia else ""
                        print(f"            {lse_pid} lotto {numero_lotto}: residuo {residuo}{unita.lower()}, scadenza {scadenza}{flag}")
            print()
finally:
    conn.close()
