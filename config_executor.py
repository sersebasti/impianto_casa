import json
import requests

from db import get_connection, get_lan_scanner_connection


def execute_config_core(
    logger,
    config_id,
):

    try:

        ################################################################
        # LOAD CONFIG
        ################################################################

        conn = get_connection()

        try:

            cur = conn.cursor()

            cur.execute("""

                SELECT
                    id,
                    device_id,
                    call_type,
                    http_method,
                    endpoint_query,
                    payload,
                    response_structure,
                    description,
                    enabled,
                    port
                FROM sensor_measurements_config
                WHERE id = ?

            """, (

                config_id,

            ))

            row = cur.fetchone()

            if row:

                row = dict(row)

        finally:

            conn.close()

        ################################################################
        # CONFIG NOT FOUND
        ################################################################

        if not row:

            return {

                "ok": False,

                "error":
                    "config non trovata",

                "config_id":
                    config_id,

                "status_code":
                    404,

            }

        ################################################################
        # ENABLED CHECK
        ################################################################

        if not row["enabled"]:

            return {

                "ok": False,

                "error":
                    "config disabilitata",

                "config_id":
                    config_id,

                "status_code":
                    400,

            }

        ################################################################
        # FAST DEVICE LOOKUP
        ################################################################

        target_ip = None

        lanscan_conn = get_lan_scanner_connection()

        try:

            cur = lanscan_conn.cursor()

            cur.execute("""

                SELECT
                    last_ip
                FROM device
                WHERE id = ?

            """, (

                row["device_id"],

            ))

            dev_row = cur.fetchone()

            if dev_row:

                dev_row = dict(dev_row)

                target_ip = (
                    dev_row.get("last_ip")
                )

        finally:

            lanscan_conn.close()

        ################################################################
        # FALLBACK LAN CHECK
        ################################################################

        if not target_ip:

            logger.warning(

                "Device IP non presente nel DB | "
                "device_id=%s | fallback LAN CHECK",

                row["device_id"]

            )

            lan_check_url = (
                "http://host.docker.internal:5001/"
                "lan_check"
            )

            try:

                lan_resp = requests.get(

                    lan_check_url,

                    timeout=20,

                )

                lan_resp.raise_for_status()

                lan_data = lan_resp.json()

            except Exception as e:

                logger.exception(
                    "LAN CHECK FAILED"
                )

                return {

                    "ok": False,

                    "error":
                        f"lan_check failed: {str(e)}",

                    "config_id":
                        config_id,

                    "lan_check_url":
                        lan_check_url,

                    "status_code":
                        500,

                }

            ################################################################
            # FIND TARGET DEVICE
            ################################################################

            target_device = None

            found_devices = (
                lan_data.get(
                    "detected_devices",
                    []
                )
            )

            for dev in found_devices:

                device_info = dev.get(
                    "device",
                    {}
                )

                current_device_id = (

                    device_info.get("id")

                    or dev.get("id")

                )

                if current_device_id == row["device_id"]:

                    target_device = dev

                    break

            ################################################################
            # DEVICE NOT FOUND
            ################################################################

            if not target_device:

                return {

                    "ok": False,

                    "error":
                        "device not found in LAN",

                    "config_id":
                        config_id,

                    "device_id":
                        row["device_id"],

                    "status_code":
                        404,

                }

            ################################################################
            # TARGET IP
            ################################################################

            target_ip = (
                target_device.get("ip")
            )

        ################################################################
        # TARGET IP VALIDATION
        ################################################################

        if not target_ip:

            return {

                "ok": False,

                "error":
                    "target ip missing",

                "config_id":
                    config_id,

                "status_code":
                    500,

            }

        ################################################################
        # PORT
        ################################################################

        port = (
            row["port"]
            or 80
        )

        ################################################################
        # ENDPOINT
        ################################################################

        endpoint_query = (
            row["endpoint_query"]
            or ""
        )

        endpoint_query = (
            endpoint_query.lstrip("/")
        )

        ################################################################
        # FINAL URL
        ################################################################

        url = (
            f"http://{target_ip}:{port}/"
            f"{endpoint_query}"
        )

        ################################################################
        # PAYLOAD
        ################################################################

        payload = None

        if row["payload"]:

            try:

                payload = json.loads(
                    row["payload"]
                )

            except Exception:

                payload = row["payload"]

        ################################################################
        # METHOD
        ################################################################

        method = (
            row["http_method"]
            or "GET"
        ).upper()

        ################################################################
        # DEBUG
        ################################################################

        logger.info(
            "[CONFIG EXECUTOR] EXECUTE"
        )

        logger.info(
            "config_id=%s",
            config_id,
        )

        logger.info(
            "device_id=%s",
            row["device_id"],
        )

        logger.info(
            "target_ip=%s",
            target_ip,
        )

        logger.info(
            "url=%s",
            url,
        )

        logger.info(
            "method=%s",
            method,
        )

        ################################################################
        # EXECUTE REQUEST
        ################################################################

        if method == "POST":

            r = requests.post(

                url,

                json=payload,

                timeout=(5, 30),

            )

        else:

            r = requests.get(

                url,

                timeout=(5, 30),

            )

        ################################################################
        # RESPONSE JSON
        ################################################################

        try:

            response_payload = r.json()

        except Exception:

            response_payload = {

                "raw_text":
                    r.text

            }

        ################################################################
        # RETURN
        ################################################################

        return {

            "ok":
                r.ok,

            "config_id":
                config_id,

            "description":
                row["description"],

            "device_id":
                row["device_id"],

            "call_type":
                row["call_type"],

            "target_ip":
                target_ip,

            "port":
                port,

            "endpoint_query":
                endpoint_query,

            "url":
                url,

            "method":
                method,

            "payload":
                payload,

            "response":
                response_payload,

            "status_code":
                r.status_code,

        }

    except Exception as e:

        logger.exception(
            "execute_config_core FAILED"
        )

        return {

            "ok": False,

            "error":
                str(e),

            "config_id":
                config_id,

            "status_code":
                500,

        }