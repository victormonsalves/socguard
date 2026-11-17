"""Punto de entrada principal para SOCGuard.

Permite ejecución única (para Windows Task Scheduler) o modo continuo (daemon).
"""

import argparse
import sys
import time
from datetime import datetime

# Asegurar codificación UTF-8 en consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from inspector import SOCGuardInspector
from logger import logger
from state_manager import StateManager


def print_banner():
    banner = """
    +===============================================================+
    |                     [+]  S O C G u a r d  [+]                 |
    |         Inspector Continuo de Automatizaciones SOC            |
    |       Deteccion Proactiva de Fallas en Logs y ServiceNow      |
    +===============================================================+
    """
    print(banner)


def show_status():
    print_banner()
    state_mgr = StateManager()
    inspector = SOCGuardInspector()
    discovered = inspector.scanner.find_initiatives_and_logs()

    print(f"[*] Directorio raíz: {inspector.scanner.root_path}")
    print(f"[*] Total de carpetas de logs descubiertas: {len(discovered)}")
    print("\nIniciativas monitoreadas:")
    seen_inits = set()
    for init_name, log_path in discovered:
        seen_inits.add(init_name)
        print(f"  • {init_name:<25} -> {log_path}")

    print(f"\nTotal iniciativas únicas: {len(seen_inits)}")

    # Incidentes activos
    incidents = state_mgr._incidents.get("initiatives", {})
    print(f"\n[*] Incidentes activos / recientes ({len(incidents)}):")
    if not incidents:
        print("  (Ninguno registrado actualmente)")
    else:
        for name, data in incidents.items():
            inc_num = data.get("incident_number", "N/A")
            created = data.get("created_at", "N/A")[:19]
            err = data.get("initial_error", "N/A")
            if len(err) > 60:
                err = err[:57] + "..."
            print(f"  • [{inc_num}] {name} ({created}) -> {err}")


def show_audit():
    print_banner()
    from log_scanner import ERROR_PATTERNS, FALSE_POSITIVE_PATTERNS
    state_mgr = StateManager()
    inspector = SOCGuardInspector()
    discovered = inspector.scanner.find_initiatives_and_logs()

    inits = {}
    for init_name, log_dir in discovered:
        inits.setdefault(init_name, []).append(log_dir)

    print(f"[*] AUDITORÍA DE INICIATIVAS Y NOVEDADES EN LOGS ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):\n")
    print(f"{'INICIATIVA':<25} | {'ESTADO':<15} | {'ÚLTIMO LOG':<28} | {'FECHA ÚLTIMA':<19} | {'DETALLE'}")
    print("-" * 125)

    for init_name, log_dirs in sorted(inits.items()):
        all_logs = []
        for ldir in log_dirs:
            for f in ldir.glob("*.log"):
                all_logs.append(f)

        if not all_logs:
            print(f"{init_name:<25} | {'SIN LOGS':<15} | {'(Sin archivos .log)':<28} | {'-':<19} | Carpeta vacía o sin logs .log")
            continue

        all_logs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        latest_file = all_logs[0]
        mtime_str = datetime.fromtimestamp(latest_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

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
            if len(last_err) > 80:
                last_err = last_err[:77] + "..."
            print(f"{init_name:<25} | {'CON NOVEDAD':<15} | {latest_file.name:<28} | {mtime_str:<19} | {last_err}")
        else:
            print(f"{init_name:<25} | {'SIN NOVEDAD':<15} | {latest_file.name:<28} | {mtime_str:<19} | Ejecución exitosa / limpia")


def main():
    parser = argparse.ArgumentParser(description="SOCGuard - Inspector de Logs y Creación de Incidentes ServiceNow")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Audita todas las iniciativas e indica si tienen o no novedad en sus logs",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        default=True,
        help="Ejecutar una única pasada y salir (Modo recomendado para Windows Task Scheduler)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Ejecutar en bucle continuo en segundo plano",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Intervalo en segundos entre chequeos en modo daemon (por defecto: 300s = 5m)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Muestra el estado de iniciativas monitoreadas e incidentes activos",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Reinicia el puntero de logs y estado de incidentes",
    )

    args = parser.parse_args()

    if args.audit:
        show_audit()
        return

    if args.status:
        show_status()
        return

    if args.reset_state:
        from config import DATA_DIR
        for f in (DATA_DIR / "inspector_state.json", DATA_DIR / "active_incidents.json"):
            if f.exists():
                f.unlink()
                print(f"[+] Eliminado archivo de estado: {f.name}")
        print("[+] Estado reiniciado correctamente.")
        return

    inspector = SOCGuardInspector()

    if args.daemon:
        print_banner()
        logger.info(f"Iniciando SOCGuard en modo DAEMON (intervalo: {args.interval}s)...")
        try:
            while True:
                inspector.run_cycle()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Detención manual solicitada por el usuario.")
            sys.exit(0)
    else:
        # Modo run-once (por defecto)
        logger.info("Ejecutando pasada única de inspección (Windows Task Scheduler)...")
        summary = inspector.run_cycle()
        sys.exit(0 if not summary.get("skipped_incidents") else 1)


if __name__ == "__main__":
    main()
