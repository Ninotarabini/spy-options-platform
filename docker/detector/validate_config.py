import os
import re
import sys

def validate():
    file_config = "config.py"
    file_client = "ibkr_client.py"
    
    # 1. Cargar variables reales de config.py
    with open(file_config, "r") as f:
        defined = {line.split('=')[0].strip() for line in f if '=' in line}

    errors = 0
    with open(file_client, "r") as f:
        for i, line in enumerate(f):
            uses = re.findall(r'config\.([a-zA-Z_0-9]+)', line)
            for var in uses:
                if var not in defined:
                    errors += 1
                    # --- AQUÍ ESTÁ LA MAGIA ---
                    # Buscamos si existe la misma palabra pero en otro formato (Mayus/Minus)
                    similar = [d for d in defined if d.lower() == var.lower()]
                    
                    print(f"\n❌ ERROR DE COHERENCIA en {file_client}:{i+1}")
                    print(f"   Pedido:  config.{var}")
                    if similar:
                        print(f"   ⚠️  ¿QUISISTE DECIR?: config.{similar[0]} ?")
                        print(f"   (El sistema detecta que los nombres no coinciden exactamente)")
                    else:
                        print(f"   ❌ NO EXISTE ninguna variable similar en {file_config}")
    return errors

if __name__ == "__main__":
    sys.exit(0 if validate() == 0 else 1)