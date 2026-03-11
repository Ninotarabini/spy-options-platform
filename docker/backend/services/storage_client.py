import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from itertools import islice
from azure.data.tables import TableServiceClient, TableClient, UpdateMode

from config import settings
from models import AnomaliesSnapshot, SpymarketSnapshot, VolumesSnapshot
from metrics import storage_operations_total

logger = logging.getLogger(__name__)

class StorageClient:
    def __init__(self):
        self.connection_string = settings.azure_storage_connection_string
        # Estandarización de nombres de tablas
        self._tables = {
            "market": "spymarket",
            "anomalies": "anomalies",
            "flow": "flow",
            "volumes": "volumes",
            "events": "marketevents"
        }
        # ✅ OPT: TableServiceClient compartido — se crea UNA vez y se reutiliza
        # Evita abrir una conexión TCP nueva en cada operación de lectura/escritura.
        self._service_client: TableServiceClient | None = None

    # ✅ MÉTODOS AUXILIARES
    def _to_rev_key_new(self, ts: float) -> str:
        """Nuevo formato para escritura/lectura (19 dígitos, positivo)"""
        max_value = 10**19 - 1
        timestamp_ticks = int(ts * 10000000)
        return str(max_value - timestamp_ticks).zfill(19)

    def _rev_key_to_timestamp(self, rowkey: str) -> float:
        """Convierte RowKey invertido a timestamp Unix"""
        try:
            max_value = 10**19 - 1
            ticks = max_value - int(rowkey)
            timestamp = ticks / 10000000
            return timestamp
        except Exception:
            return 0.0

    def _to_rev_key(self, ts: float) -> str:
        """Formato antiguo (solo para compatibilidad con datos existentes)"""
        return str(9999999999999 - int(ts * 10000000))

    def _rowkey_to_date(self, rowkey: str) -> str:
        """Convierte RowKey a fecha legible (para debugging)"""
        try:
            # Formato nuevo (positivo)
            if not rowkey.startswith('-') and len(rowkey) == 19:
                max_value = 10**19 - 1
                ticks = max_value - int(rowkey)
                timestamp = ticks / 10000000
                return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            # Formato antiguo (negativo)
            elif rowkey.startswith('-'):
                ticks = 9999999999999 - abs(int(rowkey))
                timestamp = ticks / 10000000
                return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            else:
                return rowkey
        except Exception:
            return "unknown"

    def connect(self):
        """Inicializa la conexión y asegura la existencia de tablas."""
        try:
            # ✅ OPT: Instanciar el cliente compartido aquí, una sola vez
            self._service_client = TableServiceClient.from_connection_string(self.connection_string)
            for name in self._tables.values():
                self._service_client.create_table_if_not_exists(name)
            logger.info("✅ Connected to Azure Table Storage (All Tables)")
            storage_operations_total.labels(operation="connect", status="success").inc()
        except Exception as e:
            logger.error(f"❌ Storage Connection Error: {e}")
            storage_operations_total.labels(operation="connect", status="error").inc()

    def _get_table(self, alias: str) -> TableClient:
        """✅ OPT: Reutiliza el ServiceClient existente — sin nueva conexión TCP por operación."""
        table_name = self._tables.get(alias, alias)
        if self._service_client is None:
            # Fallback por si se llama antes de connect() (no debería ocurrir)
            self._service_client = TableServiceClient.from_connection_string(self.connection_string)
        return self._service_client.get_table_client(table_name)

    # --- ESCRITURA (POST) --- TODOS USAN _to_rev_key_new AHORA

    def save_spymarket(self, market: SpymarketSnapshot) -> bool:
        try:
            client = self._get_table("market")
            entity = {
                "PartitionKey": "SPY",
                "RowKey": self._to_rev_key_new(market.timestamp),  # 🔴 CAMBIADO a nuevo formato
                "timestamp": datetime.fromtimestamp(market.timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "price": float(market.price),
                "bid": float(market.bid) if market.bid else None,
                "ask": float(market.ask) if market.ask else None,
                "last": float(market.last) if market.last else None,
                "volume": int(market.volume) if market.volume else None,
                "previous_close": float(market.previous_close),
                "market_status": market.market_status,
                "spy_change_pct": float(market.spy_change_pct),
                "atm_center": int(market.atm_center),
                "atm_min": int(market.atm_min),
                "atm_max": int(market.atm_max)
            }
            client.upsert_entity(mode=UpdateMode.REPLACE, entity=entity)
            storage_operations_total.labels(operation="save_market", status="success").inc()
            return True
        except Exception as e:
            logger.error(f"❌ Error save_spymarket: {e}")
            return False

    def save_flow(self, flow_data: dict) -> bool:
        try:
            client = self._get_table("flow")
            ts = flow_data.get("timestamp", datetime.now().timestamp())
            entity = {
                "PartitionKey": "SPY",
                "RowKey": self._to_rev_key_new(ts),  # 🔴 CAMBIADO a nuevo formato
                "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "spy_price": float(flow_data["spy_price"]),
                "cum_call_flow": float(flow_data["cum_call_flow"]),
                "cum_put_flow": float(flow_data["cum_put_flow"]),
                "net_flow": float(flow_data["net_flow"])
            }
            client.upsert_entity(mode=UpdateMode.REPLACE, entity=entity)
            return True
        except Exception as e:
            logger.error(f"❌ Error save_flow: {e}")
            return False

    

    def save_anomalies(self, anomaly: AnomaliesSnapshot) -> bool:
        try:
            client = self._get_table("anomalies")
            entity = {
                "PartitionKey": "SPY",  # ← FIJO, como en flow
                "RowKey": self._to_rev_key_new(anomaly.timestamp),
                "timestamp": datetime.fromtimestamp(anomaly.timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "strike": float(anomaly.strike),
                "option_type": anomaly.option_type,
                "bid": float(anomaly.bid) if anomaly.bid else None,
                "ask": float(anomaly.ask) if anomaly.ask else None,
                "mid_price": float(anomaly.mid_price),
                "expected_price": float(anomaly.expected_price),
                "deviation_percent": float(anomaly.deviation_percent),
                "volume": int(anomaly.volume) if anomaly.volume else 0,
                "open_interest": int(anomaly.open_interest) if anomaly.open_interest else 0,
                "severity": anomaly.severity
            }
            client.upsert_entity(mode=UpdateMode.REPLACE, entity=entity)
            return True
        except Exception as e:
            logger.error(f"❌ Error save_anomalies: {e}")
            return False

    def save_volumes(self, volume: VolumesSnapshot) -> bool:
        try:
            client = self._get_table("volumes")
            entity = {
                "PartitionKey": "SPY",
                "RowKey": self._to_rev_key_new(volume.timestamp),  # 🔴 CAMBIADO a nuevo formato
                "timestamp": datetime.fromtimestamp(volume.timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "put_vol": float(volume.put_vol),
                "call_vol": float(volume.call_vol),
                "total_vol": float(volume.total_vol)
            }
            client.upsert_entity(mode=UpdateMode.REPLACE, entity=entity)
            return True
        except Exception as e:
            logger.error(f"❌ Error save_volumes: {e}")
            return False
        
    # --- LECTURAS OPTIMIZADAS (TODAS USAN _to_rev_key_new) ---

    
    def get_spymarket_latest(self) -> Dict:
        """
        Obtiene el último registro disponible de spymarket.
        ✅ OPTIMIZADO: Usa RowKey invertido (ya funciona bien)
        """
        try:
            client = self._get_table("market")
            
            # Query sin filtro temporal - solo PartitionKey
            # Con reversed timestamps: primer resultado = más reciente (RowKey más pequeño)
            query = "PartitionKey eq 'SPY'"
            page_results = client.query_entities(query, results_per_page=1)
            
            # Retornar primer elemento sin convertir a lista
            for entity in page_results:
                return dict(entity)
            
            logger.warning("⚠️ No se encontró ningún registro en spymarket")
            return {}
            
        except Exception as e:
            logger.error(f"❌ Error get_spymarket_latest: {e}")
            return {}
    
    
    def get_spymarket(self, hours: int = 4) -> List[Dict]:
        """
        Obtiene últimas N horas REALES de datos disponibles (independiente de NOW).
        Garantiza ventana temporal de N horas calendario, aunque los datos sean antiguos.
        """
        try:
            client = self._get_table("market")
                
            # 1. Obtener registro más reciente disponible
            query_latest = "PartitionKey eq 'SPY'"
            latest_entities = list(client.query_entities(query_latest, results_per_page=1))
                
            if not latest_entities:
                logger.warning("⚠️ No hay datos en spymarket")
                return []
                
            # 2. Decodificar RowKey → timestamp
            latest_rowkey = latest_entities[0]['RowKey']
            latest_ts = self._rev_key_to_timestamp(latest_rowkey)
                
            # 3. Calcular cutoff (N horas antes del último registro)
            cutoff_ts = latest_ts - (hours * 3600)
            cutoff_rowkey = self._to_rev_key_new(cutoff_ts)
                
            # 4. Query rango temporal REAL
            query = f"PartitionKey eq 'SPY' and RowKey >= '{latest_rowkey}' and RowKey <= '{cutoff_rowkey}'"
            entities = list(client.query_entities(query))
            result = [dict(e) for e in entities]
                
            logger.info(f"📊 spymarket: {len(result)} registros en últimas {hours}h reales")
            return result
                
        except Exception as e:
            logger.error(f"❌ Error get_spymarket: {e}")
            return []

    def get_flow(self, limit: int = 1000) -> List[Dict]:
        """
        Devuelve los últimos 'limit' registros de flow (por defecto 7200 = 4h a 2s).
        SIN filtrar por tiempo, SIN lógica de mercado.
        Ordenados de más antiguo a más reciente para el frontend.
        """
        try:
            client = self._get_table("flow")
            
            # 1. Query: todos los registros con PartitionKey 'SPY'
            #    Los RowKey más pequeños = más recientes
            query = "PartitionKey eq 'SPY'"
            
            # 2. Pedir 'limit' resultados (los más recientes)
            #    Azure devuelve por defecto los más recientes primero (RowKey ASC)
            entities = list(client.query_entities(query, results_per_page=limit))
            
            # 3. Ordenar ASC para frontend (más antiguo a más reciente)
            entities.reverse()
            
            # 4. Convertir a dicts
            result = [dict(e) for e in entities]
            
            logger.info(f"📊 flow: {len(result)} registros devueltos (últimos {limit})")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error get_flow: {e}")
            return []

    def get_anomalies(self, limit: int = 50) -> List[Dict]:
        """
        Devuelve las últimas 'limit' anomalías (por defecto 50).
        SIN filtrar por tiempo, SIN lógica de mercado.
        Ordenadas por timestamp (más recientes primero en la selección,
        pero el frontend ya las gestiona).
        """
        try:
            client = self._get_table("anomalies")
            
            # 1. Query: todos los registros con PartitionKey 'SPY'
            #    Los RowKey más pequeños = más recientes
            query = "PartitionKey eq 'SPY'"
            
            # 2. Pedir 'limit' resultados (los más recientes)
            #    Multiplicamos por 2 para tener suficiente para separar por tipo
            entities = list(client.query_entities(query, results_per_page=limit * 2))
            
            if not entities:
                return []
            
            # 3. Separar por tipo (ya vienen ordenados por timestamp descendente)
            calls = []
            puts = []
            
            for entity in entities:
                e = dict(entity)
                if e.get('option_type') == 'CALL':
                    calls.append(e)
                elif e.get('option_type') == 'PUT':
                    puts.append(e)
                
                # Limitamos a 5 de cada tipo (o el valor que quieras)
                if len(calls) >= 5 and len(puts) >= 5:
                    break
            
            # 4. Normalizar timestamp (si viene como string)
            for anomaly in calls + puts:
                if 'timestamp' in anomaly and isinstance(anomaly['timestamp'], str):
                    try:
                        dt = datetime.fromisoformat(anomaly['timestamp'].replace('Z', '+00:00'))
                        anomaly['timestamp'] = int(dt.timestamp())
                    except:
                        pass
            
            logger.info(f"📊 anomalies: {len(calls)} calls, {len(puts)} puts (últimas {limit} registros)")
            return calls[:5] + puts[:5]  # 5 de cada tipo = 10 total
            
        except Exception as e:
            logger.error(f"❌ Error get_anomalies: {e}", exc_info=True)
            return []
        
    def get_volumes(self, hours: int = 72, max_results: int = 10000) -> List[Dict]:
        """
        Obtiene histórico de volúmenes.
        ✅ CORREGIDO: Usa mismo patrón que flow
        """
        try:
            client = self._get_table("volumes")
            
            # 1. Obtener registro más reciente
            latest = list(client.query_entities("PartitionKey eq 'SPY'", results_per_page=1))
            if not latest:
                logger.warning("⚠️ No hay datos en volumes")
                return []
            
            # 2. Decodificar RowKey → timestamp
            latest_rk = latest[0]['RowKey']
            latest_ts = self._rev_key_to_timestamp(latest_rk)
            
            # 3. Calcular cutoff
            cutoff_ts = latest_ts - (hours * 3600)
            cutoff_rk = self._to_rev_key_new(cutoff_ts)
            
            # 4. ✅ QUERY CORREGIDA: mismo patrón que flow
            query_filter = f"PartitionKey eq 'SPY' and RowKey ge '{cutoff_rk}' and RowKey le '{latest_rk}'"
            
            # 5. Ejecutar query con paginación
            all_entities = []
            continuation_token = None
            
            while len(all_entities) < max_results:
                if continuation_token:
                    page_results = client.query_entities(query_filter, results_per_page=1000, continuation_token=continuation_token)
                else:
                    page_results = client.query_entities(query_filter, results_per_page=1000)
                
                for entity in page_results:
                    all_entities.append(dict(entity))
                    if len(all_entities) >= max_results:
                        break
                
                continuation_token = page_results.continuation_token
                if not continuation_token:
                    break
            
            # 6. Invertir para tener recientes primero
            all_entities.reverse()
            
            logger.info(f"📊 volumes: {len(all_entities)} registros en últimas {hours}h")
            return all_entities
            
        except Exception as e:
            logger.error(f"❌ Error get_volumes: {e}")
            return []
        
    def purge_old_data(self, days: int = 7):
        """Elimina datos más antiguos que N días usando batch deletes (hasta 100 por request)."""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            rev_cutoff = self._to_rev_key_new(cutoff_date.timestamp())

            for alias in ["market", "flow", "volumes"]:
                client = self._get_table(alias)
                # RowKey MAYOR que cutoff = datos ANTIGUOS (SÍ borrar)
                query = f"PartitionKey eq 'SPY' and RowKey gt '{rev_cutoff}'"
                entities = list(client.query_entities(query_filter=query, select=["RowKey", "PartitionKey"]))

                if not entities:
                    continue

                # ✅ OPT: Batch delete — hasta 100 entidades por request
                count = 0
                batch_size = 100
                for i in range(0, len(entities), batch_size):
                    batch = entities[i : i + batch_size]
                    operations = [
                        ("delete", {"PartitionKey": e["PartitionKey"], "RowKey": e["RowKey"]})
                        for e in batch
                    ]
                    client.submit_transaction(operations)
                    count += len(batch)

                if count > 0:
                    logger.info(f"🧹 Purge: {count} registros eliminados de {alias}")

            return True
        except Exception as e:
            logger.error(f"❌ Error en purge_old_data: {e}")
            return False

# Singleton instance
storage_client = StorageClient()

    
