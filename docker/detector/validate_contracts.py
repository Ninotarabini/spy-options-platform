"""Valida coherencia de datos entre módulos"""
import re

print("🔍 Validando contratos entre módulos...")

# 1. Extraer campos que ibkr_client.py PRODUCE
with open('ibkr_client.py', 'r') as f:
    ibkr_code = f.read()
    # Buscar options_data.append({ ... })
    match = re.search(r"options_data\.append\(\{([^}]+)\}\)", ibkr_code, re.DOTALL)
    if match:
        produced_fields = set(re.findall(r"'(\w+)':", match.group(1)))
        print(f"✅ ibkr_client PRODUCE: {sorted(produced_fields)}")
    else:
        print("❌ No se encontró options_data.append")
        exit(1)

# 2. Extraer campos que volume_aggregator.py CONSUME
with open('volume_aggregator.py', 'r') as f:
    vol_code = f.read()
    consumed_fields = set(re.findall(r"option\.get\(['\"](\w+)['\"]", vol_code))
    print(f"✅ volume_aggregator CONSUME: {sorted(consumed_fields)}")

# 3. Extraer campos que anomaly_algo.py CONSUME
with open('anomaly_algo.py', 'r') as f:
    anom_code = f.read()
    # Buscar row['campo']
    anom_fields = set(re.findall(r"row\['(\w+)'\]", anom_code))
    print(f"✅ anomaly_algo CONSUME: {sorted(anom_fields)}")

# 4. Validar coincidencias
print("\n🔍 Validando compatibilidad...")

# volume_aggregator necesita 'option_type' pero ibkr_client produce 'right'
if 'option_type' in consumed_fields and 'option_type' not in produced_fields:
    if 'right' in produced_fields:
        print("⚠️  MISMATCH: volume_aggregator espera 'option_type', ibkr_client produce 'right'")
        print("   Solución: Cambiar 'right' → 'option_type' en ibkr_client.py línea ~244")
        exit(1)

# anomaly_algo necesita estos campos
required_by_anomaly = {'strike', 'volume', 'bid', 'ask'}
missing = required_by_anomaly - produced_fields
if missing:
    print(f"❌ MISMATCH: anomaly_algo necesita {missing}, no producidos por ibkr_client")
    exit(1)

# Verificar tipos en anomaly_algo
if "'volume': int(" in anom_code and "math.isnan" not in ibkr_code:
    print("⚠️  WARNING: anomaly_algo hace int(volume) pero no se valida NaN en ibkr_client")

print("\n✅ Todos los contratos son compatibles!")
