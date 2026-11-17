"""Auditoría de estado actual de todas las iniciativas y sus logs más recientes.

Ubicación: desarrollo/audit_initiatives_status.py
"""

import sys
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from state_manager import StateManager
from log_scanner import LogScanner, ERROR_PATTERNS, FALSE_POSITIVE_PATTERNS

def audit_all():
    state_mgr = StateManager()
    scanner = LogScanner(state_mgr)
    discovered = scanner.find_initiatives_and_logs()

    # Agrupar carpetas por iniciativa
    inits = {}
    for init_name, log_dir in discovered:
        inits.setdefault(init_name, []).append(log_dir)

    results = []

    for init_name, log_dirs in sorted(inits.items()):
        all_logs = []
        for ldir in log_dirs:
            for f in ldir.glob("*.log"):
                all_logs.append(f)

        if not all_logs:
            results.append({
                "initiative": init_name,
                "latest_file": "Sin archivos .log",
                "last_mtime": "-",
                "status": "SIN NOVEDAD (Sin logs)",
                "detail": "No se encontraron archivos .log en sus carpetas"
            })
            continue

        # Ordenar por fecha de modificación descendente (el más reciente primero)
        all_logs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        latest_file = all_logs[0]
        mtime_str = datetime.fromtimestamp(latest_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        # Leer las últimas 150 líneas del archivo más reciente
        errors_found = []
        try:
            with open(latest_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            tail_lines = lines[-150:] if len(lines) > 150 else lines
            for line in tail_lines:
                if any(fp.search(line) for fp in FALSE_POSITIVE_PATTERNS):
                    continue
                if any(ep.search(line) for ep in ERROR_PATTERNS):
                    errors_found.append(line.strip())
        except Exception as e:
            errors_found.append(f"Error al leer archivo: {e}")

        if errors_found:
            last_err = errors_found[-1]
            if len(last_err) > 90:
                last_err = last_err[:87] + "..."
            results.append({
                "initiative": init_name,
                "latest_file": latest_file.name,
                "last_mtime": mtime_str,
                "status": "CON NOVEDAD",
                "detail": last_err
            })
        else:
            results.append({
                "initiative": init_name,
                "latest_file": latest_file.name,
                "last_mtime": mtime_str,
                "status": "SIN NOVEDAD",
                "detail": "Última ejecución limpia / exitosa"
            })

    print(f"{'INICIATIVA':<25} | {'ESTADO':<15} | {'ÚLTIMO LOG':<30} | {'FECHA':<19} | {'DETALLE'}")
    print("-" * 125)
    for r in results:
        print(f"{r['initiative']:<25} | {r['status']:<15} | {r['latest_file']:<30} | {r['last_mtime']:<19} | {r['detail']}")

if __name__ == "__main__":
    audit_all()
