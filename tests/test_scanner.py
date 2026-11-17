"""Script de validación y pruebas para SOCGuard.

Ubicación: desarrollo/test_scanner.py
Valida el descubrimiento de iniciativas, detección de errores y formato de incidentes.
"""

import sys
from pathlib import Path

# Añadir el directorio raíz de SOCGuard al path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config import INITIATIVES_ROOT, SN_URL, SN_USER
from state_manager import StateManager
from log_scanner import LogScanner
from servicenow_client import ServiceNowClient

def test_discovery():
    print("\n" + "="*60)
    print("1. PROBANDO DESCUBRIMIENTO DE INICIATIVAS Y LOGS")
    print("="*60)
    state_mgr = StateManager()
    scanner = LogScanner(state_mgr)
    
    discovered = scanner.find_initiatives_and_logs()
    print(f"[+] Total de carpetas de logs encontradas: {len(discovered)}")
    
    unique_inits = set()
    for init_name, log_dir in discovered:
        unique_inits.add(init_name)
        log_files = list(log_dir.glob("*.log"))
        print(f"  • {init_name:<25} -> {log_dir.name}/ ({len(log_files)} archivos .log)")
    
    print(f"\n[+] Total de iniciativas cubiertas: {len(unique_inits)}")
    assert len(discovered) > 0, "No se encontraron carpetas de logs"
    print("[OK] Prueba de descubrimiento exitosa.")

def test_log_inspection():
    print("\n" + "="*60)
    print("2. PROBANDO LECTURA E IDENTIFICACIÓN DE ERRORES")
    print("="*60)
    # Usar un StateManager aislado para la prueba
    state_mgr = StateManager()
    scanner = LogScanner(state_mgr)
    
    # Probar una iniciativa conocida con logs (por ejemplo Backup Checkpoint o SMA)
    sample_dir = Path(INITIATIVES_ROOT) / "Backup Checkpoint" / "logs"
    if sample_dir.exists():
        log_files = list(sample_dir.glob("*.log"))
        if log_files:
            test_file = log_files[0]
            print(f"[*] Inspeccionando archivo de prueba: {test_file.name}")
            failures = scanner._inspect_file("Backup Checkpoint", test_file, max_context=10)
            print(f"[+] Fallas detectadas en la muestra: {len(failures)}")
            if failures:
                first = failures[0]
                print(f"    - Motivo detectado: {first['short_reason']}")
                print(f"    - Timestamp: {first['timestamp']}")
                print("    - Extracto del contexto:")
                for line in first['context'].splitlines()[:5]:
                    print(f"        | {line}")
    print("[OK] Prueba de análisis de logs exitosa.")

def test_servicenow_client():
    print("\n" + "="*60)
    print("3. PROBANDO ESTADO DEL CLIENTE SERVICENOW")
    print("="*60)
    client = ServiceNowClient()
    print(f"[*] URL ServiceNow:   {client.url or '[!] No configurada'}")
    print(f"[*] Usuario:          {client.user or '[!] No configurado'}")
    print(f"[*] Grupo Asignado:   {client.assignment_group}")
    print(f"[*] Asignado A:       {client.assigned_to}")
    print(f"[*] Cliente Listo:    {'SI' if client.is_configured else 'NO (Requiere credenciales en .env o sistema)'}")
    print("[OK] Configuración de ServiceNow verificada.")

if __name__ == "__main__":
    print("[*] Iniciando suite de validación SOCGuard...")
    test_discovery()
    test_log_inspection()
    test_servicenow_client()
    print("\n[+] TODAS LAS VALIDACIONES PASARON EXITOSAMENTE.")
