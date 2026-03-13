import os
import time
import logging
from datetime import datetime, timedelta, timezone
from azure.data.tables import TableServiceClient
import sys

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('migracion.log')
    ]
)
logger = logging.getLogger(__name__)

class AzureMigrator:
    def __init__(self, account_name: str, account_key: str):
        self.connection_string = f"DefaultEndpointsProtocol=https;AccountName={account_name};AccountKey={account_key};EndpointSuffix=core.windows.net"
        self.table_service = TableServiceClient.from_connection_string(self.connection_string)
        logger.info(f"✅ Conectado a Azure: {account_name}")
    
    def _to_new_rowkey(self, timestamp: float) -> str:
        """
        Genera un nuevo RowKey con timestamp invertido.
        Los timestamps más recientes producen números más pequeños.
        """
        max_value = 10**19 - 1
        timestamp_ticks = int(timestamp * 10_000_000)
        inverted_ticks = max_value - timestamp_ticks
        return str(inverted_ticks).zfill(19)

    def _extract_timestamp_from_entity(self, entity: dict) -> float:
        """
        Extrae el timestamp UNIX de la entidad.
        Prioriza el campo 'timestamp' de la entidad, luego el RowKey antiguo.
        """
        # Método 1: Usar el campo 'timestamp' de la entidad
        if 'timestamp' in entity:
            ts_val = entity['timestamp']
            if isinstance(ts_val, (int, float)):
                return float(ts_val)
            elif isinstance(ts_val, str):
                try:
                    dt = datetime.fromisoformat(ts_val.replace('Z', '+00:00'))
                    return dt.timestamp()
                except ValueError:
                    try:
                        return float(ts_val)
                    except ValueError:
                        pass
        
        # Método 2: Extraer del RowKey antiguo (formato: timestamp_strike_type)
        if '_' in entity.get('RowKey', ''):
            try:
                ts_part = entity['RowKey'].split('_')[0]
                return float(ts_part)
            except (ValueError, IndexError):
                pass
        
        # Método 3: Usar timestamp actual como último recurso
        logger.warning(f"⚠️ Usando timestamp actual para {entity.get('RowKey', 'unknown')}")
        return time.time()

    def migrate_anomalies(self, keep_days: int, max_records: int, delete_old: bool):
        """
        Migra SOLO las últimas 'max_records' anomalías de la tabla.
        """
        table_name = "anomalies"
        try:
            table_client = self.table_service.get_table_client(table_name)
            logger.info(f"🔄 Procesando tabla: {table_name}")

            # 1. Leer todas las entidades
            logger.info(f"📊 Leyendo entidades de {table_name}...")
            entities = list(table_client.query_entities(query_filter="PartitionKey eq 'SPY'"))
            total_leidas = len(entities)
            logger.info(f"   → {total_leidas} entidades encontradas.")

            if total_leidas == 0:
                logger.warning(f"⚠️ No hay entidades para migrar")
                return 0

            # 2. Extraer timestamp y preparar para filtrado
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=keep_days)
            cutoff_timestamp = cutoff_date.timestamp()
            logger.info(f"📅 Manteniendo registros con timestamp >= {cutoff_date.isoformat()}")

            entidades_con_ts = []
            for ent in entities:
                ts_valor = self._extract_timestamp_from_entity(ent)
                entidades_con_ts.append((ts_valor, ent))

            # 3. Filtrar por antigüedad
            entidades_filtradas = [item for item in entidades_con_ts if item[0] >= cutoff_timestamp]
            logger.info(f"🎯 {len(entidades_filtradas)} entidades dentro del rango de {keep_days} días")

            if not entidades_filtradas:
                logger.warning("⚠️ No hay entidades dentro del rango")
                return 0

            # 4. 🆕 LIMITAR A LAS MÁS RECIENTES (MAX_RECORDS)
            entidades_filtradas.sort(key=lambda x: x[0], reverse=True)  # Ordenar por timestamp descendente
            if len(entidades_filtradas) > max_records:
                logger.info(f"📊 Limitando a las {max_records} más recientes")
                entidades_filtradas = entidades_filtradas[:max_records]

            total_a_migrar = len(entidades_filtradas)
            logger.info(f"🎯 Se migrarán {total_a_migrar} entradas")

            # 5. Migrar: crear nuevas entidades
            migradas = 0
            old_rowkeys = []
            
            for ts_valor, ent in entidades_filtradas:
                try:
                    nuevo_rowkey = self._to_new_rowkey(ts_valor)
                    old_rowkeys.append(ent['RowKey'])

                    # Crear nueva entidad
                    nueva_entidad = {'PartitionKey': 'SPY', 'RowKey': nuevo_rowkey}
                    for k, v in ent.items():
                        if k not in ['PartitionKey', 'RowKey', 'Timestamp', 'etag']:
                            nueva_entidad[k] = v

                    # Asegurar que el campo timestamp sea un número
                    if 'timestamp' in nueva_entidad:
                        if isinstance(nueva_entidad['timestamp'], str):
                            try:
                                nueva_entidad['timestamp'] = int(float(nueva_entidad['timestamp']))
                            except ValueError:
                                pass
                        elif isinstance(nueva_entidad['timestamp'], (int, float)):
                            nueva_entidad['timestamp'] = int(nueva_entidad['timestamp'])

                    # Insertar
                    table_client.upsert_entity(entity=nueva_entidad, mode='replace')
                    migradas += 1

                    if migradas % 20 == 0:
                        logger.info(f"   ✅ {migradas}/{total_a_migrar} migradas")

                except Exception as e:
                    logger.error(f"   ❌ Error migrando {ent.get('RowKey', 'unknown')}: {e}")

            logger.info(f"✅ Migración completada: {migradas} nuevas entidades")

            # 6. Borrar antiguas si se solicita
            if delete_old and migradas > 0:
                logger.info(f"🧹 Borrando {len(old_rowkeys)} entidades antiguas...")
                borradas = 0
                for old_key in old_rowkeys:
                    try:
                        table_client.delete_entity(partition_key='SPY', row_key=old_key)
                        borradas += 1
                        if borradas % 20 == 0:
                            logger.info(f"   🗑️ {borradas} borradas")
                    except Exception as e:
                        logger.error(f"   ❌ Error borrando {old_key}: {e}")
                logger.info(f"✅ Borradas {borradas} entidades antiguas")
            else:
                logger.info(f"⏭️ Entidades antiguas NO borradas (DELETE_OLD={delete_old})")

            return migradas

        except Exception as e:
            logger.error(f"❌ Error crítico en migración: {e}")
            return 0

# =============================================
# EJECUCIÓN PRINCIPAL
# =============================================
if __name__ == "__main__":
    account_name = os.environ.get('AZURE_ACCOUNT_NAME', '')
    account_key = os.environ.get('AZURE_ACCOUNT_KEY', '')
    keep_days = int(os.environ.get('KEEP_DAYS', '30'))
    max_records = int(os.environ.get('MAX_RECORDS', '100'))
    delete_old = os.environ.get('DELETE_OLD', 'false').lower() == 'true'

    if not account_name or not account_key:
        logger.error("❌ Faltan credenciales de Azure")
        sys.exit(1)

    logger.info("🚀 Iniciando migración de ANOMALIES (últimas 100)")
    logger.info(f"📋 Configuración: Días={keep_days}, Máx={max_records}, Borrar={delete_old}")

    migrator = AzureMigrator(account_name, account_key)
    
    start = time.time()
    total = migrator.migrate_anomalies(keep_days, max_records, delete_old)
    elapsed = time.time() - start

    logger.info(f"\n{'='*50}")
    logger.info(f"🏁 PROCESO FINALIZADO")
    logger.info(f"⏱️ Tiempo: {elapsed:.2f} segundos")
    logger.info(f"📊 Migradas: {total}")
    logger.info(f"{'='*50}")

    with open('migracion_completada.txt', 'w') as f:
        f.write(f"Migración completada: {datetime.now()}\n")
        f.write(f"Tiempo: {elapsed:.2f} segundos\n")
        f.write(f"Entidades migradas: {total}\n")
        f.write(f"Máximo registros: {max_records}\n")
