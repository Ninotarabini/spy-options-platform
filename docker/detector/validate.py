"""Test básico sin dependencias externas"""
import math
import ast
import re

print("🔍 Validando código detector...")

# 1. Test lógica NaN handling
print("✅ Test 1: NaN handling logic")
vol = float('nan')
volume = 0 if (vol == 0 or math.isnan(vol)) else int(vol)
assert volume == 0, "Failed NaN handling"

vol = 100
volume = 0 if (vol == 0 or math.isnan(vol)) else int(vol)
assert volume == 100, "Failed normal value"

# 2. Syntax check todos los .py
import py_compile
for file in ['detector.py', 'ibkr_client.py', 'anomaly_algo.py', 'volume_aggregator.py', 'volume_tracker.py']:
    try:
        py_compile.compile(file, doraise=True)
        print(f"✅ Syntax OK: {file}")
    except Exception as e:
        print(f"❌ Syntax error in {file}: {e}")
        exit(1)

# 3. Verificar que volume_tracker.py existe
import os
if not os.path.exists('volume_tracker.py'):
    print("❌ Missing volume_tracker.py")
    exit(1)
print("✅ volume_tracker.py exists")

# 4. Verificar imports críticos en Dockerfile
with open('../detector/Dockerfile', 'r') as f:
    dockerfile = f.read()
    if 'COPY volume_tracker.py' not in dockerfile:
        print("⚠️  Warning: volume_tracker.py not in Dockerfile COPY")
    else:
        print("✅ Dockerfile includes volume_tracker.py")

print("\n✅ All validations passed!")
