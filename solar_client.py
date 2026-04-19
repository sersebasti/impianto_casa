"""
solar_client.py

Modulo che contiene gli endpoint applicativi del portale.

Cosa fa:
- usa auth.py per fare login e ottenere sessione + token
- esegue chiamate autenticate agli endpoint reali
- salva token e risposte JSON in SQLite tramite db.py

Per ora contiene solo:
- login
- lettura dati utente /apis/user/select/iotUserInfo
- lettura device state latest
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from auth import login
from db import insert_token, insert_user_info, insert_device_snapshot, insert_device_snapshot_flat
from utility import get_logger, mask_token

logger = get_logger("solar_client")


class SolarClient:
    def __init__(self, base_url: str | None = None, account: str | None = None, password: str | None = None):
        self.base_url = (base_url or os.getenv("INVERTER_BASE_URL", "https://solar.siseli.com")).rstrip("/")
        self.account = account or os.getenv("INVERTER_ACCOUNT", "")
        self.password = password or os.getenv("INVERTER_PASSWORD", "")
        self.iot_time_zone = os.getenv("IOT_TIME_ZONE", "Europe/Rome")

        self.session = None
        self.token = None
        self.login_json = None

        self.access_token_expires_at = None
        self.refresh_token = None
        self.refresh_token_expires_at = None

        logger.info(
            "SolarClient inizializzato | base_url=%s | account=%s",
            self.base_url,
            self.account,
        )

    def utc_iso_to_rome_string(self, dt_str: str | None) -> str:
        """
        Converte una data ISO UTC tipo 2026-04-18T23:15:43Z
        in stringa ora italiana tipo 2026-04-19 01:15:43.
        """
        if not dt_str:
            return ""

        dt_utc = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        dt_rome = dt_utc.astimezone(ZoneInfo("Europe/Rome"))
        return dt_rome.strftime("%Y-%m-%d %H:%M:%S")    

    def do_login(self, debug: bool = False, save_to_db: bool = True) -> dict[str, Any]:
        """
        Esegue login, salva sessione e token in memoria e opzionalmente nel DB.
        """
        logger.info("Avvio login remoto")

        result = login(self.account, self.password, debug=debug)

        self.session = result["session"]
        self.token = result["token"]
        self.login_json = result["login_json"]
        self.access_token_expires_at = result.get("access_token_expires_at")
        self.refresh_token = result.get("refresh_token")
        self.refresh_token_expires_at = result.get("refresh_token_expires_at")

        logger.info(
            "Login OK | token=%s | access_exp=%s | refresh_exp=%s",
            mask_token(self.token),
            self.access_token_expires_at,
            self.refresh_token_expires_at,
        )

        if save_to_db:
            insert_token(
                token=self.token,
                login_payload_json=json.dumps(self.login_json, ensure_ascii=False),
            )
            logger.info("Token salvato nel DB | token=%s", mask_token(self.token))

        return {
            "token": self.token,
            "login_json": self.login_json,
            "access_token_expires_at": self.access_token_expires_at,
            "refresh_token_expires_at": self.refresh_token_expires_at,
        }

    def parse_iso_z(self, dt_str: str | None) -> datetime | None:
        """
        Converte una data ISO con Z finale in datetime timezone-aware UTC.
        """
        if not dt_str:
            return None
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

    def is_expiring_soon(self, dt_str: str | None, safety_seconds: int = 300) -> bool:
        """
        True se il token è scaduto o manca poco alla scadenza.
        safety_seconds=300 => 5 minuti di margine.
        """
        dt = self.parse_iso_z(dt_str)
        if dt is None:
            logger.warning("Scadenza token assente o non leggibile: considero token da rigenerare")
            return True

        now = datetime.now(timezone.utc)
        expiring = now >= (dt - timedelta(seconds=safety_seconds))

        logger.info(
            "Controllo scadenza token | token=%s | now=%s | exp=%s | safety_seconds=%s | expiring_soon=%s",
            mask_token(self.token),
            now.isoformat(),
            dt.isoformat(),
            safety_seconds,
            expiring,
        )

        return expiring

    def ensure_login(self) -> None:
        """
        Riusa il token se ancora valido.
        Fa nuovo login solo se manca token o se è scaduto / in scadenza.
        """
        if self.session is None or self.token is None:
            logger.info("Sessione o token assenti: eseguo login")
            self.do_login()
            return

        if self.is_expiring_soon(self.access_token_expires_at, safety_seconds=300):
            logger.info(
                "Token in scadenza o scaduto: eseguo nuovo login | token=%s | access_exp=%s",
                mask_token(self.token),
                self.access_token_expires_at,
            )
            self.do_login()
        else:
            logger.info(
                "Riutilizzo token esistente | token=%s | access_exp=%s",
                mask_token(self.token),
                self.access_token_expires_at,
            )

    def _auth_headers(self) -> dict[str, str]:
        """
        Header standard per chiamate autenticate.
        """
        if not self.token:
            logger.error("Tentativo di creare header autenticati senza token")
            raise RuntimeError("Token non disponibile. Fare login prima.")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "IOT-Time-Zone": self.iot_time_zone,
            "IOT-Token": self.token,
        }

        logger.info(
            "Header auth pronti | token=%s | timezone=%s",
            mask_token(self.token),
            self.iot_time_zone,
        )

        return headers

    def get_auth(self, path: str, params: dict | None = None, timeout: int = 30) -> dict[str, Any]:
        """
        Esegue una GET autenticata.
        """
        self.ensure_login()

        logger.info(
            "GET remoto START | path=%s | params=%s | token=%s",
            path,
            params or {},
            mask_token(self.token),
        )

        response = self.session.get(
            f"{self.base_url}{path}",
            params=params or {},
            headers={
                "Accept": "application/json",
                "IOT-Time-Zone": self.iot_time_zone,
                "IOT-Token": self.token,
            },
            timeout=timeout,
        )

        logger.info(
            "GET remoto END | path=%s | status_code=%s",
            path,
            response.status_code,
        )

        response.raise_for_status()
        data = response.json()

        if data.get("code") not in (0, None):
            logger.error("Errore API GET | path=%s | response_json=%s", path, data)
            raise RuntimeError(f"Errore API su {path}: {data}")

        logger.info("GET remoto OK | path=%s | api_code=%s", path, data.get("code"))

        return data

    def post_auth(self, path: str, payload: dict | None = None, timeout: int = 30) -> dict[str, Any]:
        """
        Esegue una POST autenticata.
        """
        self.ensure_login()

        logger.info(
            "POST remoto START | path=%s | payload=%s | token=%s",
            path,
            payload or {},
            mask_token(self.token),
        )

        response = self.session.post(
            f"{self.base_url}{path}",
            json=payload or {},
            headers=self._auth_headers(),
            timeout=timeout,
        )

        logger.info(
            "POST remoto END | path=%s | status_code=%s",
            path,
            response.status_code,
        )

        response.raise_for_status()
        data = response.json()

        if data.get("code") not in (0, None):
            logger.error("Errore API POST | path=%s | response_json=%s", path, data)
            raise RuntimeError(f"Errore API su {path}: {data}")

        logger.info("POST remoto OK | path=%s | api_code=%s", path, data.get("code"))

        return data

    def get_user_info(self, save_to_db: bool = True) -> dict[str, Any]:
        """
        Endpoint reale:
        POST /apis/user/select/iotUserInfo
        """
        logger.info("Richiesta user info START")

        data = self.post_auth("/apis/user/select/iotUserInfo", {})

        if save_to_db:
            insert_user_info(
                token=self.token or "",
                payload_json=json.dumps(data, ensure_ascii=False),
            )
            logger.info("User info salvata nel DB | token=%s", mask_token(self.token))

        logger.info("Richiesta user info OK")
        return data
    
    def _field_value_display(self, fields: dict, key: str) -> str | None:
        item = fields.get(key, {})
        if not isinstance(item, dict):
            return None
        return item.get("valueDisplay")

    def get_device_state_latest(self, device_id: str, data_source: int = 1, save_to_db: bool = True) -> dict[str, Any]:
        """
        Endpoint reale:
        GET /apis/deviceState/simple/state/latest/v1?deviceId=...&dataSource=...
        """
        logger.info(
            "Richiesta device state latest START | device_id=%s | data_source=%s",
            device_id,
            data_source,
        )

        data = self.get_auth(
            "/apis/deviceState/simple/state/latest/v1",
            params={
                "deviceId": device_id,
                "dataSource": data_source,
            },
        )

        if save_to_db:
            payload_data = data.get("data", {}) or {}
            fields = payload_data.get("fields", {}) or {}

            raw_update_time = str(payload_data.get("time", ""))
            update_time = self.utc_iso_to_rome_string(raw_update_time)

            insert_device_snapshot(
                device_row_key=device_id,
                update_time=update_time,
                json_data=json.dumps(data, ensure_ascii=False),
            )

            inverter_program_version = self._field_value_display(fields, "inverterProgramMainVersion")
            inverter_program_sub_version = self._field_value_display(fields, "inverterProgramSubVersion")
            if inverter_program_version and inverter_program_sub_version:
                inverter_program_version = f"{inverter_program_version}.{inverter_program_sub_version}"

            controller_program_version = self._field_value_display(fields, "controllerProgramMainVersion")
            controller_program_sub_version = self._field_value_display(fields, "controllerProgramSubVersion")
            if controller_program_version and controller_program_sub_version:
                controller_program_version = f"{controller_program_version}.{controller_program_sub_version}"

            insert_device_snapshot_flat(
                device_row_key=device_id,
                update_time=update_time,
                inverter_program_version=inverter_program_version,
                internal_model=self._field_value_display(fields, "machType"),
                input_voltage=self._field_value_display(fields, "inputVoltage"),
                input_frequency=self._field_value_display(fields, "inputFrequency"),
                output_voltage=self._field_value_display(fields, "outputVoltage"),
                output_frequency=self._field_value_display(fields, "outputFrequency"),
                battery_voltage=self._field_value_display(fields, "batteryVoltage"),
                battery_capacity=self._field_value_display(fields, "batteryCapacity"),
                inverter_charging_current=self._field_value_display(fields, "inverterChargingCurrent"),
                load_percentage=self._field_value_display(fields, "loadPercentage"),
                device_temp=self._field_value_display(fields, "deviceTemp"),
                machine_status_code=self._field_value_display(fields, "machineStatusCode"),
                system_run_time=self._field_value_display(fields, "systemRunTime"),
                system_operation_status=self._field_value_display(fields, "systemOperationStatus"),
                battery_number_in_series=self._field_value_display(fields, "batteryNumberInSeries"),
                controller_program_version=controller_program_version,
                pv_voltage=self._field_value_display(fields, "pvVoltage"),
                controller_charging_current=self._field_value_display(fields, "controllerChargingCurrent"),
                controller_temp=self._field_value_display(fields, "controllerTemp"),
                controller_status_code=self._field_value_display(fields, "controllerStatusCode"),
                controller_connection_status=self._field_value_display(fields, "controllerConnectionStatus"),
                controller_charging_status=self._field_value_display(fields, "controllerChargingStatus"),
                inverter_charge_status=self._field_value_display(fields, "inverterChargeStatus"),
                battery_voltage_is_full=self._field_value_display(fields, "batteryVoltageIsFull"),
                controller_malfunction_alarm=self._field_value_display(fields, "controllerMalfunctionAlarm"),
                controller_warning_alarm=self._field_value_display(fields, "controllerWarningAlarm"),
                inverter_fault_alarm=self._field_value_display(fields, "inverterFaultAlarm"),
                inverter_warning_alarm=self._field_value_display(fields, "inverterWarningAlarm"),
            )

            logger.info(
                "Device snapshot raw+flat salvati nel DB | device_id=%s | raw_update_time=%s | update_time_rome=%s",
                device_id,
                raw_update_time,
                update_time,
            )

        logger.info(
            "Richiesta device state latest OK | device_id=%s | data_source=%s",
            device_id,
            data_source,
        )
        return data