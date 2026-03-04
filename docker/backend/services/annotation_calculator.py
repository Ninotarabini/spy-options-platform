# -*- coding: utf-8 -*-
"""
Annotation Calculator Service

Responsabilidad:
- Calcular índices de marcadores de mercado (15:30 open, 22:00-22:15 close)
- Usar tabla spymarket como fuente de verdad temporal
- Cachear resultados para optimización (15 min refresh)

Filosofía:
- Separation of concerns: timestamps de spymarket, no de flowhistory
- Robustez: marcadores funcionan aunque flow esté vacío
- Eficiencia: cálculo cada 15 min, no cada frame
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class AnnotationCalculator:
    """
    Calcula índices de annotations basándose en timestamps de spymarket.
    
    Estrategia:
    1. Check cada 15 min: ¿debemos mostrar marcadores ahora?
    2. Si sí → calcular índices basados en spymarket timestamps
    3. Retornar índices o dict vacío
    """
    
    def __init__(self, storage_client):
        self.storage = storage_client
        self.last_indices: Dict[str, int] = {}
        self.last_check: Optional[datetime] = None
        self.cache_duration = timedelta(minutes=15)  # Refresh cada 15 min
    
    def check_and_calculate(self, force: bool = False) -> Dict[str, int]:
        """
        Calcula índices de annotations si es necesario.
        
        Args:
            force: Forzar recálculo ignorando caché
            
        Returns:
            Dict con índices: {'marketOpenIndex': 234, 'closeZoneStart': 890, ...}
            o dict vacío si no hay marcadores activos
        """
        now = datetime.now(timezone.utc)
        
        # Optimización: usar caché si no han pasado 15 min
        if not force and self.last_check:
            time_since_check = (now - self.last_check).total_seconds()
            if time_since_check < self.cache_duration.total_seconds():
                logger.debug(f"Using cached annotations (age: {time_since_check:.0f}s)")
                return self.last_indices
        
        self.last_check = now
        
        # Obtener timestamps de spymarket (fuente de verdad temporal)
        try:
            spy_history = self.storage.get_spymarket(hours=4)
            if not spy_history:
                logger.warning("No spymarket history available for annotation calculation")
                self.last_indices = {}
                return {}
        except Exception as e:
            logger.error(f"Error fetching spymarket history: {e}")
            self.last_indices = {}
            return {}
        
        # Convertir timestamps a datetime objects
        try:
            timestamps = [
                datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
                if isinstance(item['timestamp'], str)
                else item['timestamp']
                for item in spy_history
            ]
        except Exception as e:
            logger.error(f"Error parsing timestamps: {e}")
            self.last_indices = {}
            return {}
        
        if not timestamps:
            logger.warning("Empty timestamps array after parsing")
            self.last_indices = {}
            return {}
        
        # Calcular índices basados en hora actual (CET assumed in detector)
        indices = self._calculate_indices(now, timestamps)
        
        self.last_indices = indices
        
        if indices:
            logger.info(f"Annotations calculated: {list(indices.keys())}")
        else:
            logger.debug("No active annotations for current time")
        
        return indices
    
    def _calculate_indices(self, now: datetime, timestamps: List[datetime]) -> Dict[str, int]:
        """
        Lógica de cálculo de índices.
        
        Reglas:
        - Línea apertura (15:30): Visible desde 15:30 hasta cierre (22:00)
        - Zona cierre (22:00-22:15): Visible solo en ese rango
        """
        indices = {}
        hour, minute = now.hour, now.minute
        
        # Marcador de apertura (15:30 CET)
        # Activo desde 15:30 hasta 22:00
        if (hour == 15 and minute >= 30) or (16 <= hour < 22):
            target_open = now.replace(hour=15, minute=30, second=0, microsecond=0)
            open_idx = self._find_closest_index(timestamps, target_open)
            
            if open_idx >= 0:
                indices['marketOpenIndex'] = open_idx
                logger.debug(f"Market open line at index {open_idx}")
        
        # Zona de cierre (22:00-22:15 CET)
        # Activo solo en ese rango
        if hour == 22 and 0 <= minute < 15:
            target_close_start = now.replace(hour=22, minute=0, second=0, microsecond=0)
            target_close_end = now.replace(hour=22, minute=15, second=0, microsecond=0)
            
            start_idx = self._find_closest_index(timestamps, target_close_start)
            end_idx = self._find_closest_index(timestamps, target_close_end)
            
            if start_idx >= 0 and end_idx >= 0:
                indices['closeZoneStart'] = start_idx
                indices['closeZoneEnd'] = end_idx
                logger.debug(f"Close zone at indices {start_idx}-{end_idx}")
        
        return indices
    
    def _find_closest_index(self, timestamps: List[datetime], target: datetime) -> int:
        """
        Encuentra el índice del timestamp más cercano al objetivo.
        
        Args:
            timestamps: Lista de datetime objects
            target: Timestamp objetivo
            
        Returns:
            Índice (0-based) o -1 si no hay match cercano (>30 min)
        """
        if not timestamps:
            return -1
        
        min_diff = float('inf')
        closest_idx = -1
        
        for i, ts in enumerate(timestamps):
            try:
                diff = abs((ts - target).total_seconds())
                if diff < min_diff:
                    min_diff = diff
                    closest_idx = i
            except Exception as e:
                logger.warning(f"Error comparing timestamp at index {i}: {e}")
                continue
        
        # Tolerancia: 30 minutos (1800 segundos)
        # Si el punto más cercano está a más de 30 min, no es válido
        max_tolerance = 1800
        
        if min_diff > max_tolerance:
            logger.debug(f"Closest point is {min_diff:.0f}s away (>{max_tolerance}s tolerance)")
            return -1
        
        return closest_idx
    
    def invalidate_cache(self):
        """Fuerza recálculo en próxima llamada"""
        self.last_check = None
        logger.debug("Annotation cache invalidated")
