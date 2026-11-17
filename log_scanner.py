"""Scanner inteligente de carpetas de logs de iniciativas.

Lee de forma incremental únicamente los nuevos bytes escritos en cada archivo,
detecta errores reales (Tracebacks, ERROR, CRITICAL, Fallos de ejecución)
y extrae el motivo y contexto de la falla.
"""

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import INITIATIVES_ROOT, IGNORED_DIRS, MAX_LOG_AGE_HOURS
from logger import logger
from state_manager import StateManager

# Patrones regex para detección de fallas reales
ERROR_PATTERNS = [
    re.compile(r"\b(CRITICAL|FATAL)\b", re.IGNORECASE),
    re.compile(r"\bERROR\b"),
    re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_]*Error\s*:", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_]*Exception\s*:", re.IGNORECASE),
    re.compile(r"Fallo al\b", re.IGNORECASE),
    re.compile(r"Error al\b", re.IGNORECASE),
    re.compile(r"\[\-\]\s*Error", re.IGNORECASE),
    re.compile(r"status[:\s]+FAILED", re.IGNORECASE),
]

# Patrones para descartar falsos positivos habituales
FALSE_POSITIVE_PATTERNS = [
    re.compile(r"0\s+errors", re.IGNORECASE),
    re.compile(r"errors?\s*:\s*0\b", re.IGNORECASE),
    re.compile(r"no\s+errors?", re.IGNORECASE),
    re.compile(r"sin\s+errores", re.IGNORECASE),
]


class LogScanner:
    def __init__(self, state_mgr: StateManager):
        self.state_mgr = state_mgr
        self.root_path = Path(INITIATIVES_ROOT)

    def find_initiatives_and_logs(self) -> List[Tuple[str, Path]]:
        """
        Escanea la ruta raíz para descubrir todas las carpetas 'log' o 'logs'
        de cada iniciativa de automatización.
        Retorna lista de tuplas: (nombre_iniciativa, ruta_carpeta_logs).
        """
        discovered: List[Tuple[str, Path]] = []
        if not self.root_path.exists():
            logger.error(f"Ruta de iniciativas no existe: {self.root_path}")
            return discovered

        for item in self.root_path.iterdir():
            if not item.is_dir() or item.name in IGNORED_DIRS or item.name.startswith("."):
                continue

            initiative_name = item.name

            # 1. Buscar en la raíz del proyecto
            direct_log_dirs = [sub for sub in item.iterdir() if sub.is_dir() and sub.name.lower() in ("logs", "log", "logs_f5")]
            for ldir in direct_log_dirs:
                discovered.append((initiative_name, ldir))

            # 2. Buscar en subdirectorios internos (ej. Faz/AFC/logs, Backup Palo Alto/pa_mtg/logs)
            try:
                for sub in item.rglob("*"):
                    if sub.is_dir() and sub.name.lower() in ("logs", "log") and sub not in direct_log_dirs:
                        if not any(ign in sub.parts for ign in IGNORED_DIRS):
                            discovered.append((initiative_name, sub))
            except Exception as e:
                logger.debug(f"Error recorriendo subdirectorios de {initiative_name}: {e}")

        return discovered

    def scan_new_logs(self, max_context_lines: int = 15) -> List[Dict[str, Any]]:
        """
        Escanea todos los archivos de log buscando contenido nuevo y detectando fallas.
        """
        failures: List[Dict[str, Any]] = []
        discovered_dirs = self.find_initiatives_and_logs()

        for initiative_name, log_dir in discovered_dirs:
            try:
                # Ordenar por fecha de modificación para procesar los más recientes
                log_files = sorted(
                    [p for p in log_dir.glob("*.log") if p.is_file()],
                    key=lambda p: p.stat().st_mtime
                )
            except Exception as e:
                logger.warning(f"No se pudieron leer archivos en {log_dir}: {e}")
                continue

            for log_file in log_files:
                file_failures = self._inspect_file(initiative_name, log_file, max_context_lines)
                failures.extend(file_failures)

        self.state_mgr.save_state()
        return failures

    def _inspect_file(
        self, initiative_name: str, file_path: Path, max_context: int
    ) -> List[Dict[str, Any]]:
        """Lee únicamente los nuevos bytes agregados al archivo de log."""
        failures: List[Dict[str, Any]] = []
        str_path = str(file_path.resolve())

        try:
            stat = file_path.stat()
            current_size = stat.st_size
            current_mtime = stat.st_mtime
        except OSError:
            return failures

        is_known = self.state_mgr.has_file(str_path)
        if not is_known:
            # Archivo nuevo detectado por primera vez
            file_age_hours = (time.time() - current_mtime) / 3600.0
            if file_age_hours > MAX_LOG_AGE_HOURS:
                # Archivo histórico antiguo: registrar offset al final para no disparar alertas retroactivas
                self.state_mgr.update_file_state(str_path, current_size, current_mtime)
                return failures

        last_offset = self.state_mgr.get_file_offset(str_path)

        # Si el archivo fue rotado o truncado, reiniciar desde el principio
        if current_size < last_offset:
            last_offset = 0

        # Si el tamaño no ha cambiado, no hay nada nuevo que procesar
        if current_size == last_offset:
            return failures

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(last_offset)
                new_content = f.read()
                new_offset = f.tell()

            # Actualizar estado de lectura
            self.state_mgr.update_file_state(str_path, new_offset, current_mtime)

            if not new_content.strip():
                return failures

            new_lines = new_content.splitlines()
            detected_errors = self._analyze_lines(new_lines, max_context)

            for error_info in detected_errors:
                failures.append({
                    "initiative": initiative_name,
                    "log_file": str_path,
                    "file_name": file_path.name,
                    "timestamp": error_info["timestamp"],
                    "short_reason": error_info["short_reason"],
                    "context": error_info["context"],
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                })

        except Exception as e:
            logger.error(f"Error procesando {file_path.name}: {e}")

        return failures

    def _analyze_lines(self, lines: List[str], max_context: int) -> List[Dict[str, Any]]:
        """Analiza bloques de líneas buscando errores y capturando su contexto."""
        errors_found: List[Dict[str, Any]] = []
        i = 0
        total_lines = len(lines)

        while i < total_lines:
            line = lines[i]

            # Descartar falsos positivos
            if any(fp.search(line) for fp in FALSE_POSITIVE_PATTERNS):
                i += 1
                continue

            # Buscar si coincide con patrón de falla
            matched = any(p.search(line) for p in ERROR_PATTERNS)
            if matched:
                # Extraer timestamp de la línea si existe
                ts_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}:\d{2})", line)
                line_timestamp = ts_match.group(1) if ts_match else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Limpiar motivo corto
                short_reason = line.strip()
                # Quitar prefijos comunes para dejar la causa real
                short_reason = re.sub(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,\.]\d+\s*-\s*", "", short_reason)
                short_reason = re.sub(r"^\[.*?\]\s*", "", short_reason)
                short_reason = re.sub(r"^[A-Za-z0-9_-]+\s*-\s*(ERROR|CRITICAL)\s*-\s*", "", short_reason)

                # Capturar contexto (líneas previas y posteriores para entender la falla)
                start_ctx = max(0, i - 3)
                end_ctx = min(total_lines, i + max_context)
                context_block = "\n".join(lines[start_ctx:end_ctx])

                errors_found.append({
                    "timestamp": line_timestamp,
                    "short_reason": short_reason,
                    "context": context_block,
                })

                # Avanzar el puntero para no reportar el mismo bloque de traceback 10 veces
                i = end_ctx
            else:
                i += 1

        return errors_found
