# -*- coding: utf-8 -*-
"""
Timezone Utilities - Fuente Única de Verdad

Filosofía arquitectónica:
- Azure Storage guarda en UTC (inmutable)
- Sistema interno opera 100% en CET
- Conversión SOLO en puntos de entrada/salida

Reglas:
1. Al LEER de Azure → convertir UTC a CET inmediatamente
2. TODO el procesamiento interno en CET
3. Al ESCRIBIR a Azure → convertir CET a UTC justo antes

Beneficios:
- Una sola fuente de verdad temporal
- Cálculos consistentes sin conversiones dispersas
- Debugging simplificado
- Reducción de bugs timezone
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
import pytz

# Zona horaria CET (Europe/Madrid incluye DST automáticamente)
CET = pytz.timezone('Europe/Madrid')


def now_cet() -> datetime:
    """
    Retorna la hora actual en CET.
    
    Uso: Reemplaza datetime.now(timezone.utc) en todo el código.
    
    Returns:
        datetime con tzinfo=CET
    """
    return datetime.now(CET)


def utc_to_cet(dt: datetime) -> datetime:
    """
    Convierte datetime UTC a CET.
    
    Uso: Al leer timestamps de Azure Storage.
    
    Args:
        dt: datetime en UTC (con o sin tzinfo)
        
    Returns:
        datetime en CET
    """
    if dt is None:
        return None
    
    # Si no tiene timezone, asumimos UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convertir a CET
    return dt.astimezone(CET)


def cet_to_utc(dt: datetime) -> datetime:
    """
    Convierte datetime CET a UTC.
    
    Uso: Al escribir timestamps a Azure Storage.
    
    Args:
        dt: datetime en CET (con o sin tzinfo)
        
    Returns:
        datetime en UTC
    """
    if dt is None:
        return None
    
    # Si no tiene timezone, asumimos CET
    if dt.tzinfo is None:
        dt = CET.localize(dt)
    
    # Convertir a UTC
    return dt.astimezone(timezone.utc)


def parse_timestamp_to_cet(ts_str: str) -> datetime:
    """
    Parsea un timestamp string (asumiendo UTC) y lo convierte a CET.
    
    Uso: Al procesar timestamps de Azure que vienen como strings.
    
    Args:
        ts_str: Timestamp string en formato ISO (con o sin Z)
        
    Returns:
        datetime en CET
        
    Examples:
        >>> parse_timestamp_to_cet("2026-02-24T14:30:00Z")
        datetime(2026, 2, 24, 15, 30, 0, tzinfo=CET)
        
        >>> parse_timestamp_to_cet("2026-02-24T14:30:00")
        datetime(2026, 2, 24, 15, 30, 0, tzinfo=CET)
    """
    if not ts_str:
        return None
    
    # Normalizar string (añadir +00:00 si tiene Z, o asumirlo si no tiene nada)
    if ts_str.endswith('Z'):
        ts_str = ts_str.replace('Z', '+00:00')
    elif '+' not in ts_str and not ts_str.endswith('00:00'):
        ts_str = ts_str + '+00:00'
    
    # Parsear como UTC
    dt = datetime.fromisoformat(ts_str)
    
    # Convertir a CET
    return utc_to_cet(dt)


def format_timestamp_for_azure(dt: datetime) -> str:
    """
    Formatea datetime CET como string UTC para Azure Storage.
    
    Uso: Al guardar timestamps en Azure.
    
    Args:
        dt: datetime en CET (o cualquier timezone)
        
    Returns:
        String ISO 8601 en UTC terminado en Z
        
    Example:
        >>> format_timestamp_for_azure(now_cet())
        "2026-02-24T14:30:00Z"
    """
    if dt is None:
        return None
    
    # Convertir a UTC
    dt_utc = cet_to_utc(dt) if dt.tzinfo != timezone.utc else dt
    
    # Formatear como ISO con Z
    return dt_utc.replace(tzinfo=None).isoformat() + 'Z'


def is_market_hours_cet(dt: Optional[datetime] = None) -> bool:
    """
    Determina si un timestamp CET está dentro de horario de mercado.
    Usa conversión dinámica entre ET y CET para soportar DST automáticamente.
    
    Mercado NYSE: 09:30 - 16:00 ET (siempre)
    CET/CEST: Conversión automática según DST
    
    Args:
        dt: datetime en CET (si None, usa now_cet())
        
    Returns:
        True si está en horario de mercado
    """
    if dt is None:
        dt = now_cet()
    
    # Asegurar que está en CET
    if dt.tzinfo != CET:
        dt = utc_to_cet(dt)
    
    # Convertir a ET para verificar horario NYSE
    ET = pytz.timezone('America/New_York')
    dt_et = dt.astimezone(ET)
    
    hour = dt_et.hour
    minute = dt_et.minute
    
    # NYSE: 09:30 - 16:00 ET
    if hour < 9 or hour >= 16:
        return False
    
    if hour == 9 and minute < 30:
        return False
    
    # TODO: Añadir check de NYSE holidays
    
    return True


def calculate_cutoff_cet(hours: int) -> datetime:
    """
    Calcula timestamp de corte (N horas atrás) en CET.
    
    Uso: Para queries de histórico temporal.
    
    Args:
        hours: Número de horas hacia atrás
        
    Returns:
        datetime en CET
        
    Example:
        >>> calculate_cutoff_cet(4)
        datetime(2026, 2, 24, 11, 30, 0, tzinfo=CET)  # Si ahora son 15:30
    """
    return now_cet() - timedelta(hours=hours)


# =====================================
# Utilities para compatibilidad legacy
# =====================================

def ensure_cet(dt: datetime) -> datetime:
    """
    Asegura que un datetime esté en CET, convirtiéndolo si es necesario.
    
    Útil para funciones que reciben timestamps de fuentes mixtas.
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        # Sin timezone → asumimos UTC por seguridad
        dt = dt.replace(tzinfo=timezone.utc)
    
    if dt.tzinfo == CET:
        return dt
    
    return dt.astimezone(CET)
