"""Gestor de persistencia de estado para SOCGuard.

Mantiene el control de bytes leídos en cada archivo de log (offset)
y el registro de incidentes abiertos para deduplicación.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from config import DATA_DIR, DEDUP_WINDOW_HOURS
from logger import logger

STATE_FILE = DATA_DIR / "inspector_state.json"
INCIDENTS_FILE = DATA_DIR / "active_incidents.json"


class StateManager:
    def __init__(self):
        self.state_file = STATE_FILE
        self.incidents_file = INCIDENTS_FILE
        self._state: Dict[str, Any] = self._load_json(self.state_file, default={"files": {}})
        self._incidents: Dict[str, Any] = self._load_json(self.incidents_file, default={"initiatives": {}})

    def _load_json(self, path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error al leer {path.name}: {e}. Se inicializará con valor por defecto.")
            return default

    def _save_json(self, path: Path, data: Dict[str, Any]) -> None:
        try:
            temp_path = path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.replace(path)
        except Exception as e:
            logger.error(f"Error al guardar {path.name}: {e}")

    # ──────────────────────────────────────────────────────────
    # Control de Offsets de Archivos de Log
    # ──────────────────────────────────────────────────────────
    def has_file(self, file_path: str) -> bool:
        """Indica si el archivo ya fue registrado previamente en el estado."""
        return file_path in self._state.get("files", {})

    def get_file_offset(self, file_path: str) -> int:
        file_info = self._state.get("files", {}).get(file_path)
        if not file_info:
            return 0
        return int(file_info.get("offset", 0))

    def update_file_state(self, file_path: str, offset: int, mtime: float) -> None:
        if "files" not in self._state:
            self._state["files"] = {}
        self._state["files"][file_path] = {
            "offset": offset,
            "mtime": mtime,
            "last_scan": datetime.now(timezone.utc).isoformat(),
        }

    def save_state(self) -> None:
        self._save_json(self.state_file, self._state)

    # ──────────────────────────────────────────────────────────
    # Deduplicación y Registro de Incidentes
    # ──────────────────────────────────────────────────────────
    def get_active_incident(self, initiative_name: str) -> Optional[Dict[str, Any]]:
        """
        Retorna el incidente activo para la iniciativa si existe y está dentro
        de la ventana de deduplicación (mismo día o dentro de DEDUP_WINDOW_HOURS).
        """
        initiatives = self._incidents.get("initiatives", {})
        inc_data = initiatives.get(initiative_name)
        if not inc_data:
            return None

        # Validar tiempo de antigüedad
        created_str = inc_data.get("created_at")
        if not created_str:
            return None

        try:
            created_dt = datetime.fromisoformat(created_str)
            now_dt = datetime.now(timezone.utc)
            hours_diff = (now_dt - created_dt).total_seconds() / 3600.0

            if hours_diff <= DEDUP_WINDOW_HOURS:
                return inc_data
            else:
                # Expirado de la ventana de deduplicación
                return None
        except Exception:
            return None

    def register_incident(
        self,
        initiative_name: str,
        incident_number: str,
        sys_id: str,
        short_description: str,
        initial_error: str,
    ) -> None:
        """Registra un nuevo incidente para la iniciativa."""
        if "initiatives" not in self._incidents:
            self._incidents["initiatives"] = {}

        now_iso = datetime.now(timezone.utc).isoformat()
        self._incidents["initiatives"][initiative_name] = {
            "initiative": initiative_name,
            "incident_number": incident_number,
            "sys_id": sys_id,
            "short_description": short_description,
            "initial_error": initial_error,
            "created_at": now_iso,
            "last_updated": now_iso,
            "update_count": 1,
            "status": "OPEN",
        }
        self._save_json(self.incidents_file, self._incidents)
        logger.info(f"Registrado incidente {incident_number} para iniciativa '{initiative_name}'")

    def record_incident_update(self, initiative_name: str, error_sample: str) -> None:
        """Actualiza la fecha y conteo de un incidente ya abierto."""
        inc_data = self._incidents.get("initiatives", {}).get(initiative_name)
        if inc_data:
            inc_data["last_updated"] = datetime.now(timezone.utc).isoformat()
            inc_data["update_count"] = inc_data.get("update_count", 1) + 1
            inc_data["latest_error"] = error_sample
            self._save_json(self.incidents_file, self._incidents)
