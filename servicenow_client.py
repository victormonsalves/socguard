"""Cliente REST desacoplado para ServiceNow Table API (Incidentes).

Permite crear incidentes y registrar Work Notes con reintentos y tolerancia a fallos.
"""

import time
from typing import Any, Dict, Optional
import requests
import urllib3

from config import (
    SN_URL,
    SN_USER,
    SN_PASS,
    SNOW_ASSIGNMENT_GROUP,
    SNOW_ASSIGNED_TO,
    SN_CATEGORY,
    SN_SUBCATEGORY,
    SN_IMPACT,
    SN_URGENCY,
    SN_VERIFY_SSL,
    SN_TIMEOUT,
)
from logger import logger

if not SN_VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ServiceNowClient:
    def __init__(self):
        self.url = SN_URL.rstrip("/")
        self.user = SN_USER
        self.password = SN_PASS
        self.assignment_group = SNOW_ASSIGNMENT_GROUP
        self.assigned_to = SNOW_ASSIGNED_TO
        self.category = SN_CATEGORY
        self.subcategory = SN_SUBCATEGORY
        self.impact = str(SN_IMPACT)
        self.urgency = str(SN_URGENCY)
        self.verify = SN_VERIFY_SSL
        self.timeout = SN_TIMEOUT
        self.max_retries = 3

    @property
    def is_configured(self) -> bool:
        """Verifica si las credenciales mínimas están presentes."""
        return bool(self.url and self.user and self.password)

    def _request(
        self, method: str, endpoint: str, json_data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, str]] = None
    ) -> Optional[requests.Response]:
        """Ejecuta petición HTTP a ServiceNow con reintentos."""
        if not self.is_configured:
            logger.warning("ServiceNow no configurado: Falta SN_URL, SN_USER o SN_PASS en .env o entorno.")
            return None

        url = f"{self.url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    auth=(self.user, self.password),
                    headers=headers,
                    params=params,
                    json=json_data,
                    verify=self.verify,
                    timeout=self.timeout,
                )

                if response.status_code == 429 or response.status_code >= 500:
                    wait = 2**attempt
                    logger.warning(
                        f"ServiceNow HTTP {response.status_code}. Reintento {attempt}/{self.max_retries} en {wait}s..."
                    )
                    time.sleep(wait)
                    continue

                return response

            except (requests.exceptions.RequestException, OSError) as e:
                wait = 2**attempt
                logger.warning(
                    f"Error de conexión con ServiceNow: {e}. Reintento {attempt}/{self.max_retries} en {wait}s..."
                )
                time.sleep(wait)

        logger.error(f"ServiceNow no respondió tras {self.max_retries} reintentos en {url}")
        return None

    def create_incident(
        self,
        initiative_name: str,
        short_reason: str,
        full_description: str,
        log_file: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Crea un incidente nuevo en la tabla 'incident' de ServiceNow.
        """
        short_desc = f"[FALLA AUTOMATIZACIÓN] {initiative_name}: {short_reason}"
        if len(short_desc) > 160:
            short_desc = short_desc[:157] + "..."

        payload = {
            "short_description": short_desc,
            "description": full_description,
            "category": self.category,
            "subcategory": self.subcategory,
            "impact": self.impact,
            "urgency": self.urgency,
            "assignment_group": self.assignment_group,
            "assigned_to": self.assigned_to,
        }

        params = {"sysparm_display_value": "all"}

        logger.info(f"Creando INC en ServiceNow para iniciativa '{initiative_name}'...")
        response = self._request("POST", "/api/now/table/incident", json_data=payload, params=params)

        if not response:
            return None

        if response.status_code in (200, 201):
            try:
                data = response.json().get("result", {})
                num_field = data.get("number")
                sys_field = data.get("sys_id")

                number = num_field.get("display_value", "") if isinstance(num_field, dict) else str(num_field or "")
                sys_id = sys_field.get("value", "") if isinstance(sys_field, dict) else str(sys_field or "")

                logger.info(f"[+] Incidente creado exitosamente: {number} (sys_id: {sys_id})")
                return {
                    "number": number,
                    "sys_id": sys_id,
                    "raw": data,
                }
            except Exception as e:
                logger.error(f"Error decodificando respuesta de incidente ServiceNow: {e}")
                return None
        else:
            logger.error(
                f"Error al crear incidente. Código HTTP {response.status_code}. Respuesta: {response.text}"
            )
            return None

    def add_work_note(self, sys_id: str, incident_number: str, note: str) -> bool:
        """
        Agrega una nota de trabajo (Work Note) a un incidente existente en ServiceNow.
        """
        if not sys_id:
            logger.warning(f"No se proporcionó sys_id para actualizar incidente {incident_number}")
            return False

        payload = {"work_notes": note}
        endpoint = f"/api/now/table/incident/{sys_id}"

        logger.info(f"Actualizando incidente {incident_number} con Work Note...")
        response = self._request("PATCH", endpoint, json_data=payload)

        if response and response.status_code in (200, 201):
            logger.info(f"[+] Work Note agregada con exito al incidente {incident_number}")
            return True
        else:
            err = response.text if response else "Sin respuesta"
            logger.error(f"No fue posible agregar Work Note al incidente {incident_number}: {err}")
            return False
