"""
Azure Table Storage client for anomalies persistence.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from azure.data.tables import TableServiceClient, TableClient, UpdateMode
from azure.core.exceptions import ResourceNotFoundError

from config import settings
from models import Anomaly
from metrics import storage_operations_total

logger = logging.getLogger(__name__)


class StorageClient:
    """Azure Table Storage client wrapper."""
    
    def __init__(self):
        """Initialize Table Storage client."""
        self.connection_string = settings.azure_storage_connection_string
        self.table_name = "anomalies"
        self._client: Optional[TableClient] = None
    
    def connect(self):
        """Connect to Table Storage and ensure table exists."""
        try:
            service_client = TableServiceClient.from_connection_string(
                self.connection_string
            )
            self._client = service_client.get_table_client(self.table_name)
            
            # Create table if not exists
            service_client.create_table_if_not_exists(self.table_name)
            
            logger.info(f"Connected to Table Storage: {self.table_name}")
            storage_operations_total.labels(operation="connect", status="success").inc()
        except Exception as e:
            logger.error(f"Failed to connect to Table Storage: {e}")
            storage_operations_total.labels(operation="connect", status="error").inc()
            raise
    
    def save_anomaly(self, anomaly: Anomaly) -> bool:
        """Save anomaly to Table Storage."""
        try:
            entity = {
                "PartitionKey": anomaly.symbol,
                "RowKey": f"{int(anomaly.timestamp.timestamp() * 1000)}_{anomaly.strike}_{anomaly.option_type}",
                "timestamp": anomaly.timestamp.replace(tzinfo=timezone.utc).isoformat(),
                "strike": anomaly.strike,
                "option_type": anomaly.option_type,
                "bid": anomaly.bid,
                "ask": anomaly.ask,
                "mid_price": anomaly.mid_price,
                "expected_price": anomaly.expected_price,
                "deviation_percent": anomaly.deviation_percent,
                "volume": anomaly.volume,
                "open_interest": anomaly.open_interest,
                "severity": anomaly.severity
            }
            
            self._client.upsert_entity(mode=UpdateMode.MERGE, entity=entity)
            storage_operations_total.labels(operation="save", status="success").inc()
            return True
        except Exception as e:
            logger.error(f"Failed to save anomaly: {e}")
            storage_operations_total.labels(operation="save", status="error").inc()
            return False
    
    # --- CÓDIGO EDITADO ---
    def get_recent_anomalies(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Query recent anomalies from Table Storage (ONLY last 4 hours).
        OPTIMIZED: Uses Azure query filter instead of downloading all entities.
        """
        if not self._client:
            self.connect()
        
        try:
            # 🚀 OPTIMIZACIÓN: Solo últimas 4h
            from datetime import timedelta
            # 🔥 NUEVO: Calcular último cierre de mercado
            now = datetime.now(timezone.utc)
        
            # Convertir a hora de mercado (UTC-5 = ET)
            et_hour = (now.hour - 5) % 24
            weekday = now.weekday()  # 0=Mon, 4=Fri, 6=Sun
        
            # Calcular días hacia atrás al último cierre (16:00 ET = 21:00 UTC)
            days_back = 0
            if weekday == 0:  # Lunes
                days_back = 3 if et_hour < 16 else 0  # Si es antes de cierre → Viernes
            elif weekday == 6:  # Domingo
                days_back = 2
            elif weekday == 5:  # Sábado
                days_back = 1
            elif et_hour < 16:  # Martes-Viernes antes de cierre → día anterior
                days_back = 1
            
            
            threshold = now - timedelta(days=days_back, hours=4)
        
            # 🔥 Query directo en Azure con filtro temporal
            query = f"timestamp ge datetime'{threshold.isoformat()}'"
            entities = list(self._client.query_entities(query))
        
            # Ordenamos por RowKey descendente (más recientes primero)
            entities.sort(key=lambda x: x.get('RowKey', ''), reverse=True)
        
            anomalies = []
            for entity in entities[:limit]:
                anomalies.append({
                    "timestamp": entity.get("timestamp", ""),
                    "symbol": entity.get("PartitionKey", ""),
                    "strike": entity.get("strike", 0.0),
                    "option_type": entity.get("option_type", ""),
                    "bid": entity.get("bid", 0.0),
                    "ask": entity.get("ask", 0.0),
                    "mid_price": entity.get("mid_price", 0.0),
                    "expected_price": entity.get("expected_price", 0.0),
                    "deviation_percent": entity.get("deviation_percent", 0.0),
                    "volume": entity.get("volume", 0),
                    "open_interest": entity.get("open_interest", 0),
                    "severity": entity.get("severity", "LOW")
                })
            
            storage_operations_total.labels(operation="query_anomalies", status="success").inc()
            logger.info(f"Retrieved {len(anomalies)} anomalies from last 4h")
            return anomalies
        except Exception as e:
            logger.error(f"Failed to query anomalies: {e}")
            storage_operations_total.labels(operation="query_anomalies", status="error").inc()
            return []
        
    def save_volume_snapshot(self, volume) -> bool:
        """Save volume snapshot to volumehistory table."""
        try:
            # Ensure volumehistory table exists
            service_client = TableServiceClient.from_connection_string(
                self.connection_string
            )
            volume_table = service_client.get_table_client("volumehistory")
            service_client.create_table_if_not_exists("volumehistory")
            
            # Create entity with reversed timestamp for DESC ordering
            timestamp_ticks = int(volume.timestamp.timestamp() * 1000)
            reversed_ticks = 9999999999999 - timestamp_ticks  # For DESC order
            
            entity = {
                "PartitionKey": "SPY",
                "RowKey": str(reversed_ticks),
                "timestamp": volume.timestamp.replace(tzinfo=timezone.utc).isoformat(),
                "spy_price": volume.spy_price,
                "calls_volume_atm": volume.calls_volume_atm,
                "puts_volume_atm": volume.puts_volume_atm,
                "calls_volume_delta": volume.calls_volume_delta,
                "puts_volume_delta": volume.puts_volume_delta,
                "atm_min_strike": volume.atm_range.get("min_strike", 0.0),
                "atm_max_strike": volume.atm_range.get("max_strike", 0.0),
                "strikes_count_calls": volume.strikes_count.get("calls", 0),
                "strikes_count_puts": volume.strikes_count.get("puts", 0),
                "spy_change_pct": volume.spy_change_pct
            }
            
            volume_table.upsert_entity(mode=UpdateMode.MERGE, entity=entity)
            logger.info(f"Volume snapshot saved: SPY={volume.spy_price:.2f}")
            storage_operations_total.labels(operation="save_volume", status="success").inc()
            return True
            
        except Exception as e:
            logger.error(f"Failed to save volume snapshot: {e}")
            storage_operations_total.labels(operation="save_volume", status="error").inc()
            return False
        
    def save_flow_snapshot(self, flow: dict):
        """Guardar flow snapshot en Azure Table Storage."""
        try:
            service_client = TableServiceClient.from_connection_string(
                self.connection_string
            )
            flow_table = service_client.get_table_client("flowhistory")
        
            # Timestamp para RowKey (reversed para orden DESC)
            timestamp_value = flow["timestamp"]
        
            # Convertir timestamp Unix (int) a datetime
            if isinstance(timestamp_value, (int, float)):
                dt = datetime.fromtimestamp(timestamp_value, tz=timezone.utc)
                timestamp_str = dt.isoformat().replace('+00:00', 'Z')
            else:
                # Si ya es string, procesarlo como antes
                dt = datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
                timestamp_str = timestamp_value
        
            timestamp_ticks = int(dt.timestamp() * 10000000)
            reversed_ticks = 9999999999999 - timestamp_ticks
        
        # Entity para Azure Table
            entity = {
                "PartitionKey": "SPY",
                "RowKey": str(reversed_ticks),
                "timestamp": timestamp_str,
                "spy_price": float(flow["spy_price"]),
                "cum_call_flow": float(flow["cum_call_flow"]),
                "cum_put_flow": float(flow["cum_put_flow"]),
                "net_flow": float(flow["net_flow"])
            }
        
            flow_table.create_entity(entity=entity)
            logger.info(f"✅ Flow snapshot guardado: {timestamp_str}")
        
        except Exception as e:
            logger.error(f"❌ Error guardando flow snapshot: {e}")    

    def get_volume_history(self, hours: int = 2) -> List[dict]:
        """Get volume history for the last N hours."""
        try:
            service_client = TableServiceClient.from_connection_string(
                self.connection_string
            )
            volume_table = service_client.get_table_client("volumehistory")
            
            # Calculate time threshold
            from datetime import timedelta
            threshold = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # Query all SPY volumes (reversed timestamp for DESC order)
            query = "PartitionKey eq 'SPY'"
            entities = volume_table.query_entities(query)
            
            volumes = []
            for entity in entities:
                # 1. Extraer timestamp de forma segura
                raw_ts = entity.get("timestamp")
                if not raw_ts:
                    continue
                
                timestamp = datetime.fromisoformat(raw_ts.replace('Z', '+00:00'))
                if not timestamp.tzinfo:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                
                # 2. Filtrar y Construir el diccionario con .get() y tipado
                if timestamp >= threshold:
                    volumes.append({
                        "timestamp": raw_ts,
                        "spy_price": float(entity.get("spy_price", 0.0)),
                        "calls_volume_atm": int(entity.get("calls_volume_atm", 0)),
                        "puts_volume_atm": int(entity.get("puts_volume_atm", 0)),
                        "calls_volume_delta": int(entity.get("calls_volume_delta", 0)),
                        "puts_volume_delta": int(entity.get("puts_volume_delta", 0)),
                        "atm_range": {
                            "min_strike": float(entity.get("atm_min_strike", 0.0)),
                            "max_strike": float(entity.get("atm_max_strike", 0.0))
                        },
                        "strikes_count": {
                            "calls": int(entity.get("strikes_count_calls", 0)),
                            "puts": int(entity.get("strikes_count_puts", 0))
                        },
                        "spy_change_pct": entity.get("spy_change_pct", None)
                    })
            
            storage_operations_total.labels(operation="query_volumes", status="success").inc()
            logger.info(f"Retrieved {len(volumes)} volume snapshots from last {hours}h")
            return volumes
            
        except Exception as e:
            logger.error(f"Failed to query volume history: {e}")
            storage_operations_total.labels(operation="query_volumes", status="error").inc()
            return []

    def get_flow_history(self, hours: int = 72) -> List[dict]:
        """Get flow history for the last N hours."""
        try:
            service_client = TableServiceClient.from_connection_string(
            self.connection_string
            )
            flow_table = service_client.get_table_client("flowhistory")
            # Calculate time threshold
            from datetime import timedelta
            threshold = datetime.now(timezone.utc) - timedelta(hours=hours)
        
            # Query all SPY flows (reversed timestamp for DESC order)
            query = "PartitionKey eq 'SPY'"
            entities = flow_table.query_entities(query)
        
            flows = []
            for entity in entities:
                # Extraer timestamp
                raw_ts = entity.get("timestamp")
                if not raw_ts:
                    continue
            
                # Fix timezone
                timestamp = datetime.fromisoformat(raw_ts.replace('Z', '+00:00'))
                if not timestamp.tzinfo:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            
                # Filtrar por tiempo
                if timestamp >= threshold:
                    flows.append({
                        "timestamp": raw_ts,
                        "spy_price": float(entity.get("spy_price", 0.0)),
                        "cum_call_flow": float(entity.get("cum_call_flow", 0.0)),
                        "cum_put_flow": float(entity.get("cum_put_flow", 0.0)),
                        "net_flow": float(entity.get("net_flow", 0.0))
                    })
        
            logger.info(f"✅ Flow history retrieved: {len(flows)} snapshots")
            return flows
        
        except Exception as e:
            logger.error(f"❌ Error getting flow history: {e}")
            return []


# Singleton instance
storage_client = StorageClient()
    

