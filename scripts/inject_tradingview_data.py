#!/usr/bin/env python3
"""
Procesa CSV de TradingView e inyecta en Azure Tables
Tablas: spymarket + flow
Fuente: BATS_SPY, 10S_66ec9.csv (6 marzo 2026, 18:15-22:15 CET)
"""
import os
import sys
import csv
import subprocess
from datetime import datetime, timezone
from azure.data.tables import TableServiceClient, UpdateMode

# === CONFIGURACIÓN ===
def get_connection_string():
    """Extrae connection string desde Kubernetes secret"""
    try:
        cmd = [
            "kubectl", "get", "secret", "azure-credentials",
            "-n", "spy-options-bot",
            "-o", "jsonpath={.data.AZURE_STORAGE_CONNECTION_STRING}"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        encoded = result.stdout.strip()
        
        # Decodificar base64
        import base64
        decoded = base64.b64decode(encoded).decode('utf-8')
        return decoded
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: No se pudo extraer connection string desde Kubernetes")
        print(f"   Comando: {' '.join(cmd)}")
        print(f"   Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)

CONNECTION_STRING = get_connection_string()
print(f"✅ Connection string extraída desde Kubernetes (primeros 50 chars): {CONNECTION_STRING[:50]}...")

CSV_PATH = "/home/nino/spy-options-platform/scripts/BATS_SPY, 10S_66ec9.csv"
PREVIOUS_CLOSE = 683.07  # Cierre del 5 marzo 2026

# Rango temporal CSV: 18:15-22:15 CET = 17:15-21:15 UTC (6 marzo 2026)
START_TIMESTAMP = 1772817300  # 2026-03-06 17:15:00 UTC
END_TIMESTAMP = 1772831700    # 2026-03-06 21:15:00 UTC

# CVD → Flow scaling
CVD_TO_FLOW_SCALE = 200.0
CALL_PUT_RATIO_BEARISH = 0.6  # Cuando CVD negativo, CALLs son 60% de PUTs

# === UTILIDADES ===
def reversed_rowkey(timestamp: float) -> str:
    """RowKey invertido (formato storage_client.py)"""
    max_value = 10**19 - 1
    timestamp_ticks = int(timestamp * 10000000)
    return str(max_value - timestamp_ticks).zfill(19)

def cvd_to_flow_increments(cvd_value: float, previous_cvd: float):
    """
    Convierte CVD delta a flow increments.
    
    Args:
        cvd_value: CVD actual
        previous_cvd: CVD anterior (para calcular delta)
    
    Returns:
        (call_increment, put_increment) - valores a sumar al acumulado
    """
    cvd_delta = cvd_value - previous_cvd
    
    # Escalar CVD → Flow
    flow_magnitude = abs(cvd_delta) * CVD_TO_FLOW_SCALE
    
    if cvd_delta < 0:  # Presión vendedora (PUTs dominan)
        call_increment = flow_magnitude * CALL_PUT_RATIO_BEARISH
        put_increment = flow_magnitude * (2.0 - CALL_PUT_RATIO_BEARISH)  # PUTs mayores
    else:  # Presión compradora (CALLs dominan)
        call_increment = flow_magnitude * (2.0 - CALL_PUT_RATIO_BEARISH)
        put_increment = flow_magnitude * CALL_PUT_RATIO_BEARISH
    
    return call_increment, put_increment

# === PROCESAMIENTO ===
def process_and_inject():
    """
    Lee CSV, filtra rango temporal, procesa y inserta en Azure.
    """
    print("=" * 70)
    print("🐭 INYECTOR DATOS TRADINGVIEW → AZURE TABLES")
    print("=" * 70)
    print(f"📖 CSV: {CSV_PATH}")
    print(f"⏰ Rango: 18:15-22:15 CET (6 marzo 2026)")
    print(f"📊 Previous close: ${PREVIOUS_CLOSE}")
    print("=" * 70)
    
    # Conectar a Azure
    service_client = TableServiceClient.from_connection_string(CONNECTION_STRING)
    spymarket_table = service_client.get_table_client("spymarket")
    flow_table = service_client.get_table_client("flow")
    
    # Asegurar tablas existen
    service_client.create_table_if_not_exists("spymarket")
    service_client.create_table_if_not_exists("flow")
    
    # Contadores
    total_rows = 0
    filtered_rows = 0
    spymarket_inserted = 0
    flow_inserted = 0
    
    # Estado acumulativo para flow
    cum_call_flow = 0.0
    cum_put_flow = 0.0
    previous_cvd = None
    
    print("\n📥 Procesando CSV...")
    
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            total_rows += 1
            
            try:
                timestamp = int(row['time'])
                
                # Filtrar por rango temporal
                if timestamp < START_TIMESTAMP or timestamp > END_TIMESTAMP:
                    continue
                
                filtered_rows += 1
                
                # Parse datos
                spy_price = float(row['close'])
                cvd_value = float(row['CVD (Cerrar)'])
                
                # Timestamp como datetime
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                timestamp_iso = dt.isoformat().replace("+00:00", "Z")
                
                # === SPYMARKET ===
                spy_change_pct = round(((spy_price - PREVIOUS_CLOSE) / PREVIOUS_CLOSE) * 100, 2)
                atm_center = round(spy_price)
                atm_min = atm_center - 5
                atm_max = atm_center + 5
                
                spymarket_entity = {
                    "PartitionKey": "SPY",
                    "RowKey": reversed_rowkey(timestamp),
                    "timestamp": timestamp_iso,
                    "price": spy_price,
                    "bid": round(spy_price - 0.01, 2),
                    "ask": round(spy_price + 0.01, 2),
                    "last": spy_price,
                    "volume": 5000000,  # Placeholder
                    "previous_close": PREVIOUS_CLOSE,
                    "market_status": "OPEN",
                    "spy_change_pct": spy_change_pct,
                    "atm_center": atm_center,
                    "atm_min": atm_min,
                    "atm_max": atm_max
                }
                
                spymarket_table.upsert_entity(mode=UpdateMode.REPLACE, entity=spymarket_entity)
                spymarket_inserted += 1
                
                # === FLOW ===
                # Inicializar previous_cvd en primera iteración
                if previous_cvd is None:
                    previous_cvd = cvd_value
                
                # Calcular incrementos de flow basados en CVD delta
                call_inc, put_inc = cvd_to_flow_increments(cvd_value, previous_cvd)
                
                # Acumular flow
                cum_call_flow += call_inc
                cum_put_flow -= put_inc  # PUT es negativo
                net_flow = cum_call_flow + cum_put_flow
                
                flow_entity = {
                    "PartitionKey": "SPY",
                    "RowKey": reversed_rowkey(timestamp),
                    "timestamp": timestamp_iso,
                    "spy_price": spy_price,
                    "cum_call_flow": round(cum_call_flow, 2),
                    "cum_put_flow": round(cum_put_flow, 2),
                    "net_flow": round(net_flow, 2)
                }
                
                flow_table.upsert_entity(mode=UpdateMode.REPLACE, entity=flow_entity)
                flow_inserted += 1
                
                # Actualizar previous_cvd
                previous_cvd = cvd_value
                
                # Progreso cada 100 filas
                if filtered_rows % 100 == 0:
                    print(f"  ✅ {filtered_rows} filas procesadas | SPY: ${spy_price:.2f} | Net flow: ${net_flow/1e6:.1f}M")
                
            except Exception as e:
                print(f"  ⚠️  Error fila {total_rows}: {e}")
                continue
    
    # Resumen final
    print("\n" + "=" * 70)
    print("✅ PROCESAMIENTO COMPLETO")
    print("=" * 70)
    print(f"📊 Total filas CSV: {total_rows:,}")
    print(f"✂️  Filas filtradas (18:15-22:15 CET): {filtered_rows:,}")
    print(f"💾 Registros spymarket insertados: {spymarket_inserted:,}")
    print(f"💰 Registros flow insertados: {flow_inserted:,}")
    print("")
    print(f"📈 Flow final:")
    print(f"   CALL: ${cum_call_flow/1e6:,.1f}M")
    print(f"   PUT:  ${cum_put_flow/1e6:,.1f}M")
    print(f"   NET:  ${net_flow/1e6:,.1f}M")
    print("=" * 70)

# === MAIN ===
if __name__ == "__main__":
    try:
        process_and_inject()
    except KeyboardInterrupt:
        print("\n\n⚠️  Proceso interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
