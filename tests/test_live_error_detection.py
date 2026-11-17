"""Prueba integral de ciclo de inspección y deduplicación.

Ubicación: desarrollo/test_live_error_detection.py
Crea un archivo de log temporal de prueba, ejecuta el inspector,
valida la extracción de causa y comprueba la deduplicación vía Work Notes.
"""

import sys
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from inspector import SOCGuardInspector
from state_manager import StateManager

def run_test():
    print("\n" + "="*60)
    print("PROBANDO CICLO COMPLETO DE DETECCIÓN Y DEDUPLICACIÓN")
    print("="*60)
    
    # Crear carpeta de prueba de iniciativa dummy
    dummy_init_dir = ROOT_DIR.parent / "Dummy_Test_Automation"
    dummy_log_dir = dummy_init_dir / "logs"
    dummy_log_dir.mkdir(parents=True, exist_ok=True)
    test_log_file = dummy_log_dir / "automation_test_run.log"
    
    try:
        # 1. Escribir primera falla en el log
        print("\n[PASO 1] Escribiendo primer fallo en el log...")
        with open(test_log_file, "w", encoding="utf-8") as f:
            f.write("2026-10-21 23:30:00 - main_service - INFO - Iniciando tarea de sincronizacion\n")
            f.write("2026-10-21 23:30:15 - main_service - ERROR - Fallo al conectar con base de datos: Timeout tras 30s\n")
            f.write("2026-10-21 23:30:16 - main_service - INFO - Reintentando operacion...\n")
        
        inspector = SOCGuardInspector()
        summary1 = inspector.run_cycle()
        print(f"[+] Resumen Pasada 1:")
        print(f"    - Fallas detectadas: {summary1['total_failures_detected']}")
        print(f"    - Incidentes creados: {summary1['created_incidents']}")
        print(f"    - Work notes agregadas: {summary1['updated_incidents']}")
        
        assert summary1['total_failures_detected'] >= 1, "No se detecto la falla esperada"
        assert len(summary1['created_incidents']) == 1, "Deberia haberse creado un incidente"
        
        inc_id = summary1['created_incidents'][0]
        print(f"\n[OK] Incidente creado correctamente: {inc_id}")
        
        # 2. Escribir segunda falla subsecuente en el mismo archivo (simulando reintento fallido)
        print("\n[PASO 2] Escribiendo segundo fallo (reintento) para probar deduplicación...")
        with open(test_log_file, "a", encoding="utf-8") as f:
            f.write("2026-10-21 23:35:00 - main_service - ERROR - Traceback (most recent call last):\n")
            f.write("    File 'task.py', line 45, in run\n")
            f.write("ConnectionRefusedError: Error critico de socket en puerto 5432\n")
        
        summary2 = inspector.run_cycle()
        print(f"[+] Resumen Pasada 2:")
        print(f"    - Fallas detectadas: {summary2['total_failures_detected']}")
        print(f"    - Incidentes creados: {summary2['created_incidents']}")
        print(f"    - Work notes agregadas: {summary2['updated_incidents']}")
        
        assert len(summary2['created_incidents']) == 0, "No debe crear un INC duplicado"
        assert len(summary2['updated_incidents']) == 1, "Debe agregar una Work Note al INC existente"
        
        print("\n[OK] Deduplicación exitosa: Se agrego Work Note en lugar de abrir otro ticket.")
        
    finally:
        # Limpiar carpeta dummy y registros de prueba
        if dummy_init_dir.exists():
            shutil.rmtree(dummy_init_dir, ignore_errors=True)
            print(f"[+] Carpeta dummy eliminada: {dummy_init_dir.name}")
        
        # Limpiar registro dummy en state_manager
        state_mgr = StateManager()
        if "Dummy_Test_Automation" in state_mgr._incidents.get("initiatives", {}):
            del state_mgr._incidents["initiatives"]["Dummy_Test_Automation"]
            state_mgr._save_json(state_mgr.incidents_file, state_mgr._incidents)
        for key in list(state_mgr._state.get("files", {}).keys()):
            if "Dummy_Test_Automation" in key:
                del state_mgr._state["files"][key]
        state_mgr.save_state()
        print("[+] Estado limpiado.")

if __name__ == "__main__":
    run_test()
