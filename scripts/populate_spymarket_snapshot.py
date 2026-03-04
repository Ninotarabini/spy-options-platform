#!/usr/bin/env python3
"""
Script de inicialización: Crea 1 snapshot actual en spymarket.

Propósito:
- Obtener precio SPY actual + EOD de IBKR
- POST al backend /spymarket
- Frontend puede mostrar bloque superior inmediatamente

Uso:
    python3 populate_spymarket_snapshot.py
"""

import sys
import time
import requests
from datetime import datetime
from pathlib import Path

# Añadir path del detector para reutilizar IBKRClient
sys.path.insert(0, str(Path(__file__).parent.parent / "docker" / "detector"))

from ibkr_client import IBKRClient
from config import settings


def get_market_status() -> str:
    """Detecta estado actual del mercado basado en hora ET."""
    from datetime import datetime
    
    now = datetime.utcnow()
    et_hour = (now.hour - 5) % 24  # UTC-5 = ET (aproximado)
    weekday = now.weekday()  # 0=Mon, 6=Sun
    
    # Weekend
    if weekday in [5, 6]:
        return "CLOSED"
    
    # Market hours (9:30 - 16:00 ET = 14:30 - 21:00 UTC)
    if 14 <= et_hour < 21:
        if et_hour == 14 and now.minute < 30:
            return "PREMARKET"
        return "OPEN"
    
    # After hours
    if 21 <= et_hour < 23:
        return "AFTERHOURS"
    
    return "CLOSED"


def main():
    print("=" * 60)
    print("SPY MARKET SNAPSHOT INITIALIZATION")
    print("=" * 60)
    
    # 1. Conectar IBKR
    print("\n[1/5] Conectando a IBKR...")
    ibkr_client = IBKRClient(config=settings)
    
    if not ibkr_client.ensure_connected():
        print("❌ ERROR: No se pudo conectar a IBKR")
        sys.exit(1)
    
    print("✅ Conectado a IBKR")
    
    # 2. Obtener datos SPY
    print("\n[2/5] Obteniendo datos SPY...")
    spy_price = ibkr_client.get_spy_price()
    
    if spy_price is None:
        print("❌ ERROR: No se pudo obtener precio SPY")
        sys.exit(1)
    
    print(f"✅ Precio SPY: ${spy_price:.2f}")
    
    # 3. Obtener EOD (yesterday's close)
    eod_yesterday = ibkr_client.spy_prev_close
    
    if eod_yesterday is None or eod_yesterday <= 0:
        print("⚠️  WARNING: EOD no disponible, usando fallback")
        eod_yesterday = 693.15  # Fallback temporal
    
    print(f"✅ EOD Yesterday: ${eod_yesterday:.2f}")
    
    # 4. Preparar payload
    print("\n[3/5] Preparando payload...")
    
    timestamp = int(time.time())
    market_status = get_market_status()
    
    payload = {
        "timestamp": timestamp,
        "price": round(spy_price, 2),
        "previous_close": round(eod_yesterday, 2),
        "market_status": market_status,
        "bid": round(getattr(ibkr_client, 'spy_bid', None) or spy_price, 2),
        "ask": round(getattr(ibkr_client, 'spy_ask', None) or spy_price, 2),
        "last": round(spy_price, 2),
        "volume": getattr(ibkr_client, 'spy_volume', None)
    }
    
    print(f"✅ Payload preparado:")
    print(f"   - Timestamp: {datetime.fromtimestamp(timestamp).isoformat()}")
    print(f"   - Price: ${payload['price']}")
    print(f"   - EOD: ${payload['previous_close']}")
    print(f"   - Status: {market_status}")
    
    # 5. POST al backend
    print("\n[4/5] Enviando al backend...")
    
    backend_url = f"{settings.backend_url}/spymarket"
    print(f"   URL: {backend_url}")
    
    try:
        response = requests.post(
            backend_url,
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        
        result = response.json()
        print("✅ Snapshot guardado correctamente")
        print(f"   - SPY Change: {result.get('spy_change_pct', 'N/A')}%")
        print(f"   - ATM Range: {result.get('atm_range', {}).get('min', 'N/A')}-{result.get('atm_range', {}).get('max', 'N/A')}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR al enviar al backend: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text[:200]}")
        sys.exit(1)
    
    # 6. Verificar en Azure
    print("\n[5/5] Verificando en Azure Table Storage...")
    time.sleep(2)  # Esperar persistencia
    
    verify_url = f"{settings.backend_url}/api/spymarket/snap_last_4h"
    
    try:
        verify_response = requests.get(verify_url, timeout=5)
        verify_response.raise_for_status()
        
        data = verify_response.json()
        
        if data.get('spy_change_pct') is not None:
            print("✅ Verificación exitosa - Datos completos en Azure:")
            print(f"   - Price: ${data.get('price', 'N/A')}")
            print(f"   - Change: {data.get('spy_change_pct', 'N/A')}%")
            print(f"   - ATM: {data.get('atm_min', 'N/A')}-{data.get('atm_max', 'N/A')}")
            print(f"   - Status: {data.get('market_status', 'N/A')}")
        else:
            print("⚠️  WARNING: Snapshot guardado pero sin campos calculados")
            
    except Exception as e:
        print(f"⚠️  WARNING: No se pudo verificar (backend puede no estar listo): {e}")
    
    # Cleanup
    print("\n[CLEANUP] Cerrando conexión IBKR...")
    ibkr_client.shutdown()
    
    print("\n" + "=" * 60)
    print("✅ INICIALIZACIÓN COMPLETADA")
    print("=" * 60)
    print("\nEl frontend ahora puede:")
    print("  1. Mostrar bloque superior con datos actuales")
    print("  2. Dibujar línea previous close en el chart")
    print("\nA las 15:15 CET el detector tomará el relevo automáticamente.")


if __name__ == "__main__":
    main()
