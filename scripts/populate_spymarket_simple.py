#!/usr/bin/env python3
"""
Script simplificado: Crea 1 snapshot en spymarket sin conectar IBKR.
Usa últimos datos conocidos + estimación razonable.
"""

import requests
import time
from datetime import datetime

# Configuración
BACKEND_URL = "http://192.168.1.134"  # Ajusta si es diferente

def main():
    print("=" * 60)
    print("SPY MARKET SNAPSHOT - MODO SIMPLIFICADO")
    print("=" * 60)
    
    # Datos base (última sesión conocida)
    spy_price = 688.99  # Del screenshot actual
    eod_yesterday = 684.80  # Estimado razonable
    
    print(f"\n[INFO] Usando datos actuales del dashboard:")
    print(f"  - SPY Price: ${spy_price}")
    print(f"  - EOD Yesterday: ${eod_yesterday}")
    
    # Preparar payload
    timestamp = int(time.time())
    
    payload = {
        "timestamp": timestamp,
        "price": spy_price,
        "previous_close": eod_yesterday,
        "market_status": "CLOSED",  # Mercado cerrado ahora
        "bid": spy_price - 0.05,
        "ask": spy_price + 0.05,
        "last": spy_price,
        "volume": None
    }
    
    print(f"\n[1/3] Payload preparado:")
    print(f"  - Timestamp: {datetime.fromtimestamp(timestamp)}")
    print(f"  - Price: ${payload['price']}")
    print(f"  - EOD: ${payload['previous_close']}")
    
    # POST al backend
    print(f"\n[2/3] Enviando a {BACKEND_URL}/spymarket...")
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/spymarket",
            json=payload,
            timeout=10
        )
        
        if response.status_code >= 400:
            print(f"❌ ERROR: Status {response.status_code}")
            print(f"Response: {response.text[:300]}")
            return
        
        result = response.json()
        print("✅ Snapshot guardado correctamente")
        print(f"  - SPY Change: {result.get('spy_change_pct', 'N/A')}%")
        print(f"  - ATM Range: {result.get('atm_range', {})}")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return
    
    # Verificar
    print(f"\n[3/3] Verificando...")
    time.sleep(1)
    
    try:
        verify = requests.get(f"{BACKEND_URL}/api/spymarket/latest", timeout=5)
        data = verify.json()
        
        print("✅ Verificación exitosa:")
        print(f"  - Price: ${data.get('price')}")
        print(f"  - Change: {data.get('spy_change_pct')}%")
        print(f"  - ATM: {data.get('atm_min')}-{data.get('atm_max')}")
        print(f"  - Previous Close: ${data.get('previous_close')}")
        
    except Exception as e:
        print(f"⚠️  Verificación falló: {e}")
    
    print("\n" + "=" * 60)
    print("✅ COMPLETADO")
    print("=" * 60)
    print("\nRecarga el frontend (Ctrl+F5) para ver los cambios")

if __name__ == "__main__":
    main()
