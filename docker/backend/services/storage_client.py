"""
Azure Table Storage client for anomalies persistence.
"""
import logging
from datetime import datetime
from typing import List, Optional
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
    
    def get_recent_anomalies(self, limit: int = 100) -> List[Anomaly]:
        """Get recent anomalies from Table Storage."""
        try:
            # Query last N entities
            entities = self._client.query_entities(
                query_filter="PartitionKey eq 'SPY'",
                select=["timestamp", "strike", "option_type", "bid", "ask", 
                       "mid_price", "expected_price", "deviation_percent",
                       "volume", "open_interest", "severity"]
            )
            
            anomalies = []
            for entity in list(entities)[:limit]:
                anomalies.append(Anomaly(
                    timestamp=datetime.fromisoformat(entity["timestamp"]),
                    symbol="SPY",
                    strike=entity["strike"],
                    option_type=entity["option_type"],
                    bid=entity["bid"],
                    ask=entity["ask"],
                    mid_price=entity["mid_price"],
                    expected_price=entity["expected_price"],
                    deviation_percent=entity["deviation_percent"],
                    volume=entity["volume"],
                    open_interest=entity["open_interest"],
                    severity=entity["severity"]
                ))
            
            storage_operations_total.labels(operation="query", status="success").inc()
            return anomalies
        except Exception as e:
            logger.error(f"Failed to query anomalies: {e}")
            storage_operations_total.labels(operation="query", status="error").inc()
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
            threshold = datetime.utcnow() - timedelta(hours=hours)
            
            # Query all SPY volumes (reversed timestamp for DESC order)
            query = "PartitionKey eq 'SPY'"
            entities = volume_table.query_entities(query)
            
            volumes = []
            for entity in entities:
                timestamp = datetime.fromisoformat(entity["timestamp"])
                if timestamp >= threshold:
                    volumes.append({
                        "timestamp": entity["timestamp"],
                        "spy_price": entity["spy_price"],
                        "calls_volume_atm": entity["calls_volume_atm"],
                        "puts_volume_atm": entity["puts_volume_atm"],
                        "atm_range": {
                            "min_strike": entity["atm_min_strike"],
                            "max_strike": entity["atm_max_strike"]
                        },
                        "strikes_count": {
                            "calls": entity["strikes_count_calls"],
                            "puts": entity["strikes_count_puts"]
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
    

