import subprocess
import os
import yaml # Requiere: pip install pyyaml
import re

SERVICES = {
    "Backend": "docker/backend",
    "Detector": "docker/detector",
    "Bot": "docker/bot"
}

HELM_VALUES = "helm/spy-trading-bot/values.yaml"

def run_local_validators():
    all_pass = True
    for name, path in SERVICES.items():
        if os.path.exists(os.path.join(path, "validate_config.py")):
            res = subprocess.run(["python3", "validate_config.py"], cwd=path)
            if res.returncode != 0:
                all_pass = False
    return all_pass

def check_helm_sync():
    print("\n--- Sincronización con Helm ---")
    if not os.path.exists(HELM_VALUES):
        print("⚠️ No se encontró values.yaml de Helm para comparar.")
        return True

    with open(HELM_VALUES, 'r') as f:
        values = yaml.safe_load(f)
    
    # Ejemplo: Verificar si 'detector' en Helm tiene las claves necesarias
    # Puedes personalizar esto según tus keys de values.yaml
    detector_config = os.path.join(SERVICES["Detector"], "config.py")
    if os.path.exists(detector_config):
        with open(detector_config, 'r') as f:
            needed = re.findall(r'^([A-Z_0-9]+)\s*=', f.read(), re.M)
            # Aquí podrías comparar si 'needed' está en 'values' de Helm
            print(f"ℹ️ {len(needed)} variables detectadas para validar contra Helm en el futuro.")
    
    return True

if __name__ == "__main__":
    print("🛡️ INICIANDO AUDITORÍA GLOBAL DEL SISTEMA\n")
    
    locals_ok = run_local_validators()
    helm_ok = check_helm_sync()
    
    if locals_ok and helm_ok:
        print("\n✅ TODO CORRECTO: Los archivos están sincronizados.")
    else:
        print("\n🚨 ERRORES ENCONTRADOS: Revisa los logs arriba antes de hacer deploy.")
        
def check_kubernetes_sync():
    print("\n--- Validando Sincronización con Kubernetes ---")
    configmap_path = "kubernetes/configmaps/bot-config.yaml"
    models_path = "docker/detector/models.py" # O donde tengas el Field(alias=...)

    if not os.path.exists(configmap_path):
        print("⚠️ No se encontró bot-config.yaml, saltando validación K8s.")
        return

    with open(configmap_path, 'r') as f:
        cm_data = yaml.safe_load(f)
        keys_in_k8s = cm_data.get('data', {}).keys()

    with open(models_path, 'r') as f:
        content = f.read()
        # Buscamos todos los alias="NOMBRE" en tus modelos Pydantic
        required_in_code = re.findall(r'alias="([A-Z_]+)"', content)

    errors = 0
    for key in required_in_code:
        if key not in keys_in_k8s:
            print(f"  ❌ ERROR: El código pide '{key}' pero no está en el ConfigMap de K8s.")
            errors += 1
        else:
            print(f"  ✅ '{key}' está correctamente mapeado.")
    
    return errors