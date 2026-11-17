"""Inspector central de SOCGuard.

Orquesta el escaneo de logs, detección de fallas, deduplicación y
creación o actualización de incidentes en ServiceNow.
"""

import socket
from datetime import datetime, timezone
from typing import Any, Dict, List

from logger import logger
from state_manager import StateManager
from log_scanner import LogScanner
from servicenow_client import ServiceNowClient


class SOCGuardInspector:
    def __init__(self):
        self.state_mgr = StateManager()
        self.scanner = LogScanner(self.state_mgr)
        self.sn_client = ServiceNowClient()
        self.hostname = socket.gethostname()

    def run_cycle(self) -> Dict[str, Any]:
        """
        Ejecuta un ciclo completo de inspección:
        1. Escanea logs de todas las iniciativas.
        2. Procesa cada falla detectada aplicando deduplicación.
        3. Crea INC o añade Work Note según corresponda.
        """
        start_time = datetime.now()
        logger.info(f"=== INICIANDO CICLO DE INSPECCIÓN SOCGUARD ({start_time.strftime('%Y-%m-%d %H:%M:%S')}) ===")

        # 1. Escanear fallas nuevas
        failures = self.scanner.scan_new_logs()
        logger.info(f"Escaneo finalizado. Total de fallas nuevas detectadas: {len(failures)}")

        created_incidents: List[str] = []
        updated_incidents: List[str] = []
        skipped_incidents: List[str] = []

        # 2. Agrupar fallas por iniciativa para no duplicar en el mismo ciclo
        failures_by_initiative: Dict[str, List[Dict[str, Any]]] = {}
        for fail in failures:
            init = fail["initiative"]
            failures_by_initiative.setdefault(init, []).append(fail)

        # 3. Procesar cada iniciativa con fallas
        for initiative, init_failures in failures_by_initiative.items():
            # Tomamos la falla principal/más representativa
            primary_fail = init_failures[0]
            short_reason = primary_fail["short_reason"]
            log_file = primary_fail["log_file"]
            file_name = primary_fail["file_name"]
            timestamp = primary_fail["timestamp"]

            # Si hay múltiples fallas en la misma corrida, combinamos el contexto
            contexts = [f"--- Evento {idx+1} ({f['timestamp']}) ---\n{f['context']}" for idx, f in enumerate(init_failures[:3])]
            full_context = "\n\n".join(contexts)

            active_inc = self.state_mgr.get_active_incident(initiative)

            if active_inc:
                # ─── CASO A: Ya existe INC activo hoy -> Agregar Work Note ────────
                inc_num = active_inc.get("incident_number", "INC_ACTIVO")
                sys_id = active_inc.get("sys_id", "")

                work_note = (
                    f"[ACTUALIZACIÓN SOCGuard - NUEVA FALLA DETECTADA]\n"
                    f"Hora: {timestamp}\n"
                    f"Archivo: {file_name}\n"
                    f"Iniciativa: {initiative}\n"
                    f"Motivo: {short_reason}\n\n"
                    f"Extracto de log:\n"
                    f"--------------------------------------------------\n"
                    f"{full_context}\n"
                    f"--------------------------------------------------"
                )

                if self.sn_client.is_configured:
                    ok = self.sn_client.add_work_note(sys_id, inc_num, work_note)
                    if ok:
                        updated_incidents.append(inc_num)
                        self.state_mgr.record_incident_update(initiative, short_reason)
                else:
                    logger.warning(f"[SIMULACIÓN] Work Note para {inc_num} ({initiative}): {short_reason}")
                    updated_incidents.append(f"{inc_num} (simulado)")
                    self.state_mgr.record_incident_update(initiative, short_reason)

            else:
                # ─── CASO B: No existe INC activo -> Crear nuevo INC ──────────────
                full_description = (
                    f"===========================================================\n"
                    f"ALERTA AUTOMÁTICA DE INCIDENTE SOC - TAREA FALLIDA\n"
                    f"===========================================================\n"
                    f"Iniciativa / Automatización: {initiative}\n"
                    f"Servidor: {self.hostname}\n"
                    f"Archivo de Log: {log_file}\n"
                    f"Fecha/Hora Detección: {timestamp}\n\n"
                    f"MOTIVO DE LA FALLA:\n"
                    f"{short_reason}\n\n"
                    f"EVIDENCIA EXTRAÍDA DEL LOG:\n"
                    f"-----------------------------------------------------------\n"
                    f"{full_context}\n"
                    f"-----------------------------------------------------------\n"
                    f"Ticket generado automáticamente por SOCGuard Inspector."
                )

                if self.sn_client.is_configured:
                    inc_res = self.sn_client.create_incident(
                        initiative_name=initiative,
                        short_reason=short_reason,
                        full_description=full_description,
                        log_file=log_file,
                    )
                    if inc_res:
                        new_num = inc_res.get("number", "INC_GENERADO")
                        new_sys_id = inc_res.get("sys_id", "")
                        self.state_mgr.register_incident(
                            initiative_name=initiative,
                            incident_number=new_num,
                            sys_id=new_sys_id,
                            short_description=short_reason,
                            initial_error=short_reason,
                        )
                        created_incidents.append(new_num)
                    else:
                        skipped_incidents.append(initiative)
                else:
                    # Modo simulación cuando no hay credenciales activas
                    sim_num = f"INC_SIM_{datetime.now().strftime('%H%M%S')}"
                    logger.warning(
                        f"[SIMULACIÓN] Credenciales de ServiceNow no configuradas. "
                        f"Simulando creación de {sim_num} para '{initiative}': {short_reason}"
                    )
                    self.state_mgr.register_incident(
                        initiative_name=initiative,
                        incident_number=sim_num,
                        sys_id="mock_sys_id",
                        short_description=short_reason,
                        initial_error=short_reason,
                    )
                    created_incidents.append(sim_num)

        elapsed = (datetime.now() - start_time).total_seconds()
        summary = {
            "elapsed_seconds": round(elapsed, 2),
            "total_failures_detected": len(failures),
            "initiatives_with_errors": list(failures_by_initiative.keys()),
            "created_incidents": created_incidents,
            "updated_incidents": updated_incidents,
            "skipped_incidents": skipped_incidents,
        }

        logger.info(
            f"=== CICLO COMPLETADO en {elapsed:.2f}s | "
            f"Fallas: {len(failures)} | "
            f"INCs Creados: {len(created_incidents)} | "
            f"Work Notes: {len(updated_incidents)} ==="
        )

        return summary
