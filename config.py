"""Configuración central para SOCGuard."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env local si existe
ENV_FILE = Path(__file__).resolve().parent / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)

def get_env_var(name: str, default: str = "") -> str:
    """Obtiene una variable desde el entorno de proceso o sistema."""
    val = os.getenv(name)
    if val is not None and val.strip() != "":
        return val.strip()
    return default

# Directorio raíz del proyecto SOCGuard
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Ruta donde residen todas las iniciativas a monitorear
_default_root = str(BASE_DIR.parent)
INITIATIVES_ROOT = Path(get_env_var("INITIATIVES_ROOT", _default_root))

# Carpetas o nombres a ignorar durante el escaneo
IGNORED_DIRS = {
    "AutoSOC",
    "SOCGuard",
    ".git",
    "desarrollo",
    "venv",
    ".venv",
    "__pycache__",
    ".idea",
    ".vscode",
    "node_modules",
}

# Credenciales y endpoints de ServiceNow
# Se aceptan variantes habituales (SN_URL o SERVICENOW_INSTANCE_URL)
SN_URL = (
    get_env_var("SN_URL")
    or get_env_var("SERVICENOW_INSTANCE_URL")
    or get_env_var("SNOW_URL")
    or "https://<instancia>.service-now.com/"
).rstrip("/")

SN_USER = (
    get_env_var("SN_USER")
    or get_env_var("SERVICENOW_USERNAME")
    or get_env_var("SNOW_USER")
    or ""
)

SN_PASS = (
    get_env_var("SN_PASS")
    or get_env_var("SERVICENOW_PASSWORD")
    or get_env_var("SNOW_PASS")
    or ""
)

SNOW_ASSIGNMENT_GROUP = get_env_var("SNOW_ASSIGNMENT_GROUP", "grupo-asignacion-soc")
SNOW_ASSIGNED_TO = get_env_var("SNOW_ASSIGNED_TO", "SOAR")
SN_CATEGORY = get_env_var("SN_CATEGORY", "Software")
SN_SUBCATEGORY = get_env_var("SN_SUBCATEGORY", "Job Failure")
SN_IMPACT = get_env_var("SN_IMPACT", "3")
SN_URGENCY = get_env_var("SN_URGENCY", "3")
SN_VERIFY_SSL = get_env_var("SN_VERIFY_SSL", "false").lower() in ("true", "1", "yes")
SN_TIMEOUT = int(get_env_var("SN_TIMEOUT", "30"))

# Ventana de deduplicación en horas
DEDUP_WINDOW_HOURS = int(get_env_var("DEDUP_WINDOW_HOURS", "24"))

# Antigüedad máxima de logs a inspeccionar en primera pasada (horas)
# Evita alertar sobre archivos de logs antiguos o meses anteriores
MAX_LOG_AGE_HOURS = int(get_env_var("MAX_LOG_AGE_HOURS", "24"))

# Nivel de log interno
LOG_LEVEL = get_env_var("LOG_LEVEL", "INFO")

