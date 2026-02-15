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
                "timestamp": anomaly.timestamp.isoformat(),
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
        Query recent anomalies from Table Storage (Ordered by newest first).
        """
        if not self._client:
            self.connect()
            
        try:
            # Obtenemos las entidades
            entities = list(self._client.list_entities())
            
            # Ordenamos por RowKey (que contiene el timestamp) de forma descendente
            # Esto garantiza que las anomalías de hoy salgan antes que las de ayer
            entities.sort(key=lambda x: x.get('RowKey', ''), reverse=True)
            
            anomalies = []
            for entity in entities:
                anomalies.append({
                    "timestamp": entity.get("timestamp", ""),
                    "symbol": entity.get("PartitionKey", ""),  # Azure usa PartitionKey para el Symbol
                    "strike": entity.get("strike", 0.0),
                    "option_type": entity.get("option_type", ""), # COHERENTE CON AZURE
                    "bid": entity.get("bid", 0.0),
                    "ask": entity.get("ask", 0.0),
                    "mid_price": entity.get("mid_price", 0.0),    # COHERENTE CON AZURE
                    "expected_price": entity.get("expected_price", 0.0),
                    "deviation_percent": entity.get("deviation_percent", 0.0), # COHERENTE CON AZURE
                    "volume": entity.get("volume", 0),
                    "open_interest": entity.get("open_interest", 0),
                    "severity": entity.get("severity", "LOW")
                })
            
            storage_operations_total.labels(operation="query_anomalies", status="success").inc()
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
                "timestamp": volume.timestamp.isoformat(),
                "spy_price": volume.spy_price,
                "calls_volume_atm": volume.calls_volume_atm,
                "puts_volume_atm": volume.puts_volume_atm,
                "atm_min_strike": volume.atm_range.get("min_strike", 0.0),
                "atm_max_strike": volume.atm_range.get("max_strike", 0.0),
                "strikes_count_calls": volume.strikes_count.get("calls", 0),
                "strikes_count_puts": volume.strikes_count.get("puts", 0)
            }
            
            volume_table.upsert_entity(mode=UpdateMode.MERGE, entity=entity)
            logger.info(f"Volume snapshot saved: SPY={volume.spy_price:.2f}")
            storage_operations_total.labels(operation="save_volume", status="success").inc()
            return True
            
        except Exception as e:
            logger.error(f"Failed to save volume snapshot: {e}")
            storage_operations_total.labels(operation="save_volume", status="error").inc()
            return False

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
                
                timestamp = datetime.fromisoformat(raw_ts)
                
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
                        }
                    })
            
            storage_operations_total.labels(operation="query_volumes", status="success").inc()
            logger.info(f"Retrieved {len(volumes)} volume snapshots from last {hours}h")
            return volumes
            
        except Exception as e:
            logger.error(f"Failed to query volume history: {e}")
            storage_operations_total.labels(operation="query_volumes", status="error").inc()
            return []


# Singleton instance
storage_client = StorageClient()
    

