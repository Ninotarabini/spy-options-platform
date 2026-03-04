#!/usr/bin/env python3
"""
Genera 4h de datos sintéticos para spy-options-platform
Tablas: spymarket (simple) + flow (acumulado)
"""
import os
import sys
import random
from datetime import datetime, timedelta, timezone

# Azure SDK
from azure.data.tables import TableServiceClient, UpdateMode

# === CONFIGURACIÓN ===
CONNECTION_STRING = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
if not CONNECTION_STRING:
    print("❌ ERROR: Set AZURE_STORAGE_CONNECTION_STRING environment variable")
    sys.exit(1)

HOURS = 4
INTERVAL_SEC = 60  # 1 punto por minuto
TOTAL_POINTS = HOURS * 60  # 240 puntos

# Parámetros SPY realistas
SPY_BASE = 592.50
SPY_VOLATILITY = 0.20  # Max variación por minuto
PREVIOUS_CLOSE = 591.80

# === UTILIDADES ===
def reversed_rowkey(timestamp: float) -> str:
    """RowKey invertido (formato storage_client.py)"""
    max_value = 10**19 - 1
    timestamp_ticks = int(timestamp * 10000000)
    return str(max_value - timestamp_ticks).zfill(19)

def random_walk(current: float, volatility: float) -> float:
    """Precio siguiente con movimiento aleatorio"""
    change = random.uniform(-volatility, volatility)
    return round(current + change, 2)

# === GENERADORES ===
def generate_spymarket_data():
    """
    Genera datos SPY market.
    1 snapshot por minuto = estado del mercado.
    """
    print(f"\n📊 Generando {TOTAL_POINTS} snapshots SPY market...")
    
    service_client = TableServiceClient.from_connection_string(CONNECTION_STRING)
    table_client = service_client.get_table_client("spymarket")
    
    # Asegurar tabla existe
    service_client.create_table_if_not_exists("spymarket")
    
    # Timestamp inicial (now - 4h)
    end_time = datetime.now(timezone.utc)
    current_time = end_time - timedelta(hours=HOURS)
    
    spy_price = SPY_BASE
    count = 0
    
    while current_time <= end_time:
        ts = int(current_time.timestamp())
        
        # Random walk del precio
        spy_price = random_walk(spy_price, SPY_VOLATILITY)
        
        # Calcular derivados (como hace el backend)
        spy_change_pct = round(((spy_price - PREVIOUS_CLOSE) / PREVIOUS_CLOSE) * 100, 2)
        atm_center = round(spy_price)
        atm_min = atm_center - 5
        atm_max = atm_center + 5
        
        # Entidad Azure
        entity = {
            "PartitionKey": "SPY",
            "RowKey": reversed_rowkey(ts),
            "timestamp": current_time.isoformat().replace("+00:00", "Z"),
            "price": spy_price,
            "bid": round(spy_price - 0.01, 2),
            "ask": round(spy_price + 0.01, 2),
            "last": spy_price,
            "volume": random.randint(1000000, 5000000),
            "previous_close": PREVIOUS_CLOSE,
            "market_status": "OPEN",
            "spy_change_pct": spy_change_pct,
            "atm_center": atm_center,
            "atm_min": atm_min,
            "atm_max": atm_max
        }
        
        table_client.upsert_entity(mode=UpdateMode.REPLACE, entity=entity)
        count += 1
        
        if count % 60 == 0:
            print(f"  ✅ {count}/{TOTAL_POINTS} registros | SPY: ${spy_price:.2f}")
        
        current_time += timedelta(seconds=INTERVAL_SEC)
    
    print(f"✅ SPY market: {count} registros insertados")
    return spy_price  # Retornar último precio para flow

def generate_flow_data(final_spy_price):
    """
    Genera datos flow acumulado.
    Tendencia realista basada en momentum del SPY.
    """
    print(f"\n💰 Generando {TOTAL_POINTS} snapshots flow...")
    
    service_client = TableServiceClient.from_connection_string(CONNECTION_STRING)
    table_client = service_client.get_table_client("flow")
    
    # Asegurar tabla existe
    service_client.create_table_if_not_exists("flow")
    
    # Timestamp inicial
    end_time = datetime.now(timezone.utc)
    current_time = end_time - timedelta(hours=HOURS)
    
    # Flow inicial (empieza en 0)
    cum_call_flow = 0.0
    cum_put_flow = 0.0
    spy_price = SPY_BASE
    
    # Determinar sesgo según momentum final
    momentum = final_spy_price - SPY_BASE
    if momentum > 0:
        call_weight = 1.5  # Más flujo a calls si sube
        put_weight = 0.8
    else:
        call_weight = 0.8
        put_weight = 1.5  # Más flujo a puts si baja
    
    count = 0
    
    while current_time <= end_time:
        ts = int(current_time.timestamp())
        
        # Incrementos aleatorios (acumulado)
        call_increment = random.uniform(500000, 2000000) * call_weight
        put_increment = random.uniform(500000, 2000000) * put_weight
        
        cum_call_flow += call_increment
        cum_put_flow -= put_increment  # PUT es negativo
        net_flow = cum_call_flow + cum_put_flow
        
        # Actualizar precio SPY (random walk)
        spy_price = random_walk(spy_price, SPY_VOLATILITY)
        
        # Entidad Azure
        entity = {
            "PartitionKey": "SPY",
            "RowKey": reversed_rowkey(ts),
            "timestamp": current_time.isoformat().replace("+00:00", "Z"),
            "spy_price": spy_price,
            "cum_call_flow": round(cum_call_flow, 2),
            "cum_put_flow": round(cum_put_flow, 2),
            "net_flow": round(net_flow, 2)
        }
        
        table_client.upsert_entity(mode=UpdateMode.REPLACE, entity=entity)
        count += 1
        
        if count % 60 == 0:
            print(f"  ✅ {count}/{TOTAL_POINTS} registros | Net: ${net_flow/1e6:.1f}M")
        
        current_time += timedelta(seconds=INTERVAL_SEC)
    
    print(f"✅ Flow: {count} registros insertados")
    print(f"   Final → CALL: ${cum_call_flow/1e6:.1f}M | PUT: ${cum_put_flow/1e6:.1f}M | Net: ${net_flow/1e6:.1f}M")

# === MAIN ===
if __name__ == "__main__":
    print("=" * 60)
    print("🐭 GENERADOR DATOS SINTÉTICOS 4H")
    print("=" * 60)
    
    # 1. SPY Market (simple)
    final_price = generate_spymarket_data()
    
    # 2. Flow (acumulado con sesgo realista)
    generate_flow_data(final_price)
    
    print("\n" + "=" * 60)
    print("✅ GENERACIÓN COMPLETA")
    print(f"📊 {TOTAL_POINTS} puntos por tabla")
    print(f"⏱️  Intervalo: {INTERVAL_SEC}s")
    print(f"🕐 Rango: últimas {HOURS}h")
    print("=" * 60)
