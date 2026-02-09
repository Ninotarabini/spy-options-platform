import time
import jwt
from fastapi import APIRouter
from config import settings

router = APIRouter()

HUB_NAME = "spyoptions"

@router.get("/negotiate")
def negotiate():
    endpoint = settings.azure_signalr_endpoint
    access_key = settings.azure_signalr_access_key

    client_url = f"{endpoint}/client/?hub={HUB_NAME}"

    payload = {
        "aud": client_url,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600
    }

    token = jwt.encode(payload, access_key, algorithm="HS256")

    return {
        "url": client_url,
        "accessToken": token
    }
