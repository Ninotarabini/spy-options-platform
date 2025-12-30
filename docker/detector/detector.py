import asyncio
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("SPY Anomaly Detector starting...")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    
    # Placeholder - conectará a IBKR en Fase 9
    while True:
        logger.info("Detector running - waiting for IBKR integration (Phase 9)")
        await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Detector stopped by user")
