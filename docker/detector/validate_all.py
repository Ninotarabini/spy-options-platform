"""Validación completa de contratos y consistencia entre módulos"""
import re
import ast

print("🔍 VALIDACIÓN EXHAUSTIVA DEL SISTEMA")
print("=" * 60)

errors = []
warnings = []

# ===========================================================================
# 1. EXTRAER CAMPOS PRODUCIDOS POR ibkr_client.py
# ===========================================================================
print("\n📋 Paso 1: Analizando ibkr_client.py...")
with open('ibkr_client.py', 'r') as f:
    ibkr_code = f.read()

# Buscar options_data.append({ ... })
match = re.search(r"options_data\.append\(\{([^}]+)\}\)", ibkr_code, re.DOTALL)
if not match:
    errors.append("❌ No se encontró options_data.append en ibkr_client.py")
else:
    produced_fields = {}
    for line in match.group(1).split('\n'):
        field_match = re.search(r"'(\w+)':\s*(.+),", line.strip())
        if field_match:
            field_name = field_match.group(1)
            field_value = field_match.group(2).strip()
            produced_fields[field_name] = field_value
    
    print(f"✅ Campos PRODUCIDOS: {sorted(produced_fields.keys())}")
    for field, expr in produced_fields.items():
        print(f"   - {field}: {expr}")

# ===========================================================================
# 2. EXTRAER CAMPOS CONSUMIDOS POR CADA MÓDULO
# ===========================================================================
modules_to_check = {
    'volume_aggregator.py': [],
    'anomaly_algo.py': [],
    'detector.py': []
}

for module, _ in modules_to_check.items():
    print(f"\n📋 Paso 2: Analizando {module}...")
    try:
        with open(module, 'r') as f:
            code = f.read()
        
        # Buscar option.get('campo') o option['campo']
        get_fields = set(re.findall(r"option\.get\(['\"](\w+)['\"]", code))
        bracket_fields = set(re.findall(r"option\['(\w+)'\]", code))
        
        # Buscar df['campo'] en pandas
        df_fields = set(re.findall(r"df\['(\w+)'\]", code))
        
        # Buscar row['campo']
        row_fields = set(re.findall(r"row\['(\w+)'\]", code))
        
        all_consumed = get_fields | bracket_fields | df_fields | row_fields
        modules_to_check[module] = all_consumed
        
        if all_consumed:
            print(f"✅ Campos CONSUMIDOS: {sorted(all_consumed)}")
        else:
            print(f"⚠️  No consume campos de options_data")
            
    except FileNotFoundError:
        warnings.append(f"⚠️  {module} no encontrado")

# ===========================================================================
# 3. VALIDAR CONSISTENCIA DE NOMBRES
# ===========================================================================
print(f"\n🔍 Paso 3: Validando consistencia de nombres...")

all_consumed_fields = set()
for fields in modules_to_check.values():
    all_consumed_fields.update(fields)

# Verificar si campos consumidos existen en producidos
# Campos calculados internamente (no vienen de options_data)
CALCULATED_FIELDS = {'moneyness', 'price_change_pct', 'z_score', 'severity', 'deviation'}
# Campos calculados internamente por anomaly_algo (no vienen de options_data)
CALCULATED_FIELDS = {'moneyness', 'price_change_pct', 'z_score', 'severity', 'deviation'}

# Verificar si campos consumidos existen en producidos (excluyendo calculados)
missing_fields = (all_consumed_fields - set(produced_fields.keys())) - CALCULATED_FIELDS

if missing_fields:
    errors.append(f"❌ CAMPOS FALTANTES: {missing_fields}")
    errors.append("   Estos campos son consumidos pero NO producidos por ibkr_client.py")
    
    # Sugerir correcciones
    for missing in missing_fields:
        if missing == 'right' and 'option_type' in produced_fields:
            errors.append(f"   💡 Sugerencia: Cambiar '{missing}' → 'option_type' en módulos consumidores")
        elif missing == 'option_type' and 'right' in produced_fields:
            errors.append(f"   💡 Sugerencia: Cambiar 'right' → 'option_type' en ibkr_client.py")
else:
    print("✅ Todos los campos consumidos están siendo producidos")

# ===========================================================================
# 4. VALIDAR CONVERSIONES DE TIPO
# ===========================================================================
print(f"\n🔍 Paso 4: Validando conversiones de tipo...")

# Verificar int(volume) sin validación NaN
for module, fields in modules_to_check.items():
    if 'volume' in fields:
        with open(module, 'r') as f:
            code = f.read()
        
        if "int(row['volume'])" in code or "int(option['volume'])" in code:
            if 'math.isnan' not in ibkr_code or 'volume = 0 if' not in ibkr_code:
                errors.append(f"❌ {module} hace int(volume) pero ibkr_client no valida NaN")
            else:
                print(f"✅ {module} y ibkr_client manejan correctamente NaN en volume")

# ===========================================================================
# 5. VALIDAR CAMPOS OPCIONALES VS REQUERIDOS
# ===========================================================================
print(f"\n🔍 Paso 5: Validando uso de .get() vs ['campo']...")

for module, _ in modules_to_check.items():
    try:
        with open(module, 'r') as f:
            code = f.read()
        
        # Campos accedidos con [] (pueden fallar si no existen)
        required_access = set(re.findall(r"(?:option|row)\['(\w+)'\]", code))
        # Campos accedidos con .get() (seguros)
        safe_access = set(re.findall(r"(?:option|row)\.get\(['\"](\w+)['\"]", code))
        
        risky_fields = required_access - safe_access
        if risky_fields and module != 'ibkr_client.py':
            warnings.append(f"⚠️  {module} accede a {risky_fields} sin .get() (puede fallar)")
            
    except FileNotFoundError:
        pass

# ===========================================================================
# 6. VERIFICAR DOCKERFILE
# ===========================================================================
print(f"\n🔍 Paso 6: Verificando Dockerfile...")

with open('../detector/Dockerfile', 'r') as f:
    dockerfile = f.read()

required_files = ['detector.py', 'anomaly_algo.py', 'ibkr_client.py', 'volume_aggregator.py', 'volume_tracker.py']
for file in required_files:
    if f'COPY {file}' not in dockerfile:
        errors.append(f"❌ Dockerfile no copia {file}")
    else:
        print(f"✅ {file} incluido en Dockerfile")

# ===========================================================================
# RESUMEN FINAL
# ===========================================================================
print("\n" + "=" * 60)
print("📊 RESUMEN DE VALIDACIÓN")
print("=" * 60)

if errors:
    print(f"\n❌ ERRORES CRÍTICOS ({len(errors)}):")
    for error in errors:
        print(error)
    print("\n🚫 NO PROCEDER CON BUILD/DEPLOY hasta corregir errores")
    exit(1)

if warnings:
    print(f"\n⚠️  ADVERTENCIAS ({len(warnings)}):")
    for warning in warnings:
        print(warning)

if not errors and not warnings:
    print("\n✅ TODAS LAS VALIDACIONES PASARON")
    print("✅ Sistema listo para build y deploy")
else:
    print("\n⚠️  Hay advertencias pero no errores críticos")
    print("✅ Sistema puede proceder con build y deploy")

print("=" * 60)

# Campos calculados internamente (no vienen de options_data)
CALCULATED_FIELDS = {'moneyness', 'price_change_pct', 'z_score', 'severity', 'deviation'}

# Filtrar campos calculados antes de validar
missing_fields = (all_consumed_fields - set(produced_fields.keys())) - CALCULATED_FIELDS
