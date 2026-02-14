import os
import re
import sys

def validate():
    print(f"--- Revisando Backend ---")
    if not os.path.exists("config.py"):
        print("❌ Error: No se encuentra config.py en backend")
        return 1

    # 1. Extraer variables definidas en config.py
    with open("config.py", "r") as f:
        content = f.read()
        defined = set(re.findall(r'^([A-Z_0-9]+)\s*=', content, re.M))

    # 2. Buscar usos en la carpeta y subcarpeta 'services'
    errors = 0
    for root, _, files in os.walk("."):
        for file in files:
            if file.endswith(".py") and file not in ["config.py", "validate_config.py"]:
                path = os.path.join(root, file)
                with open(path, "r") as f:
                    # Busca patrones: config.VARIABLE o variables directamente importadas
                    uses = re.findall(r'config\.([A-Z_0-9]+)', f.read())
                    for var in uses:
                        if var not in defined:
                            print(f"  ❌ Variable '{var}' no definida en config.py (Usada en: {path})")
                            errors += 1
    return errors

if __name__ == "__main__":
    sys.exit(0 if validate() == 0 else 1)