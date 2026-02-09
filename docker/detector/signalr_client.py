import base64
import hmac
import hashlib
import time
import requests
import json
from urllib.parse import quote_plus

from config import settings


def _generate_access_token(endpoint: str, access_key: str) -> str:
    expiry = int(time.time()) + 3600
    encoded_uri = quote_plus(endpoint.lower())

    string_to_sign = f"{encoded_uri}\n{expiry}"
    signature = hmac.new(
        base64.b64decode(access_key),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    encoded_signature = quote_plus(base64.b64encode(signature))
    return f"SharedAccessSignature sr={encoded_uri}&sig={encoded_signature}&se={expiry}"


def broadcast_anomalies(anomalies_payload: dict) -> None:
    if not settings.azure_signalr_connection_string:
        return  # SignalR opcional, no rompe el detector

    # Parse connection string
    parts = dict(
        item.split("=", 1)
        for item in settings.azure_signalr_connection_string.split(";")
        if "=" in item
    )

    endpoint = parts["Endpoint"].replace("https://", "")
    access_key = parts["AccessKey"]

    hub = "spyoptions"
    url = f"https://{endpoint}/api/v1/hubs/{hub}"

    token = _generate_access_token(url, access_key)

    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
    }

    body = {
        "target": "anomalies",
        "arguments": [anomalies_payload],
    }

    response = requests.post(
        f"{url}/:send",
        headers=headers,
        data=json.dumps(body),
        timeout=5,
    )

    response.raise_for_status()

