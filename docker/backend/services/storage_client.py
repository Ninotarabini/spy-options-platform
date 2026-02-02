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
        except:
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
        except:
            return "unknown"

    def connect(self):
        """Inicializa la conexión y asegura la existencia de tablas."""
        try:
            service_client = TableServiceClient.from_connection_string(self.connection_string)
            for name in self._tables.values():
                service_client.create_table_if_not_exists(name)
            logger.info("✅ Connected to Azure Table Storage (All Tables)")
            storage_operations_total.labels(operation="connect", status="success").inc()
        except Exception as e:
            logger.error(f"❌ Storage Connection Error: {e}")
            storage_operations_total.labels(operation="connect", status="error").inc()

    def _get_table(self, alias: str) -> TableClient:
        table_name = self._tables.get(alias, alias)
        return TableServiceClient.from_connection_string(self.connection_string).get_table_client(table_name)

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

    def save_anomalies(self, anomaly: AnomaliesSnapshot) -> bool:
        try:
            client = self._get_table("anomalies")
            entity = {
                "PartitionKey": anomaly.symbol,
                "RowKey": f"{anomaly.timestamp}_{anomaly.strike}_{anomaly.option_type}",  # ✅ Formato especial, NO CAMBIAR
                "timestamp": datetime.fromtimestamp(anomaly.timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                **anomaly.dict()
            }
            client.upsert_entity(mode=UpdateMode.REPLACE, entity=entity)
            return True
        except Exception as e:
            logger.error(f"❌ Error save_anomalies: {e}")
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

    def get_flow(self, hours: int = 8, max_results: int = 10000) -> List[Dict]:
        """
        Obtiene últimas N horas de flow.
        ✅ OPTIMIZADA: Query simple con limit 1500 (benchmarked: ~2.12s, cubre 4.17h con scan 10s)
        """
        try:
            client = self._get_table("flow")
            
            # 1. Query simple con HARD LIMIT usando islice (detiene paginación)
            query = "PartitionKey eq 'SPY'"
            entities = list(islice(client.query_entities(query), 1500))
            
            if not entities:
                logger.warning("⚠️ No hay datos en flow")
                return []
            
            # 2. Invertir para cronológico (más antiguo primero → más reciente último)
            #    Frontend espera orden ASC para renderizar correctamente
            entities.reverse()
            
            # 3. Convertir a dicts
            result = [dict(e) for e in entities]
            
            logger.info(f"📊 flow: {len(result)} registros (~{len(result)*10/3600:.1f}h con scan 10s)")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error get_flow: {e}")
            return []

    def get_anomalies(self, limit: int = 5, hours: int = 48) -> List[Dict]:
        """
        Obtiene últimas anomalías (limit PUT + limit CALL).
        ✅ OPTIMIZADA: Query simple sin filtro temporal (benchmarked: ~1.85s)
        """
        try:
            client = self._get_table("anomalies")
            
            # 1. Query simple con HARD LIMIT usando islice (detiene paginación)
            query = "PartitionKey eq 'SPY'"
            entities = list(islice(client.query_entities(query), 50))
            
            if not entities:
                logger.warning("⚠️ No hay datos en anomalies")
                return []
            
            # 2. Separar por tipo
            calls = [e for e in entities if e.get('option_type') == 'CALL']
            puts = [e for e in entities if e.get('option_type') == 'PUT']
            
            # 3. Ordenar DESC por timestamp (extraído de RowKey)
            calls.sort(key=lambda x: int(x['RowKey'].split('_')[0]) if '_' in x['RowKey'] else 0, reverse=True)
            puts.sort(key=lambda x: int(x['RowKey'].split('_')[0]) if '_' in x['RowKey'] else 0, reverse=True)
            
            # 4. Tomar top N de cada tipo
            result = calls[:limit] + puts[:limit]
            result.sort(key=lambda x: int(x['RowKey'].split('_')[0]) if '_' in x['RowKey'] else 0, reverse=True)
            
            # 5. Convertir a dicts
            result = [dict(e) for e in result]
            
            # 6. Normalizar timestamp: convertir string ISO → Unix timestamp (int)
            for anomaly in result:
                if 'timestamp' in anomaly and isinstance(anomaly['timestamp'], str):
                    try:
                        # "2026-01-27T16:38:23.435173" → 1706372303
                        anomaly['timestamp'] = int(datetime.fromisoformat(anomaly['timestamp']).timestamp())
                    except (ValueError, AttributeError):
                        # Si falla, usar el timestamp del RowKey como fallback
                        if '_' in anomaly.get('RowKey', ''):
                            anomaly['timestamp'] = int(anomaly['RowKey'].split('_')[0])
            
            logger.info(f"📊 anomalies: {len(result)} registros (C:{len(calls[:limit])} P:{len(puts[:limit])})")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error get_anomalies: {e}")
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
        """Elimina datos más antiguos que N días."""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            rev_cutoff = self._to_rev_key_new(cutoff_date.timestamp())
                
            for alias in ["market", "flow", "volumes"]:
                client = self._get_table(alias)
                # RowKey MENOR que cutoff = datos RECIENTES (NO borrar)
                # RowKey MAYOR que cutoff = datos ANTIGUOS (SÍ borrar)
                query = f"PartitionKey eq 'SPY' and RowKey gt '{rev_cutoff}'"
                    
                entities = client.query_entities(query_filter=query, select=["RowKey", "PartitionKey"])
                            
                count = 0
                for entity in entities:
                    client.delete_entity(row_key=entity['RowKey'], partition_key=entity['PartitionKey'])
                    count += 1
                            
                if count > 0:
                    logger.info(f"🧹 Purge: {count} registros eliminados de {alias}")
                    
            return True
        except Exception as e:
            logger.error(f"❌ Error en purge_old_data: {e}")
            return False

# Singleton instance
storage_client = StorageClient()
    
