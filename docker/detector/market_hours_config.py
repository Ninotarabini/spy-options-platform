# market_hours_config.py
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import os

class MarketHoursConfig:
    """Configuración dinámica de horarios de mercado"""
    
    # Horarios fijos de USA (ET)
    MARKET_OPEN_ET = "09:30"
    MARKET_CLOSE_ET = "16:00"
    
    # Fechas de cambio de horario 2026 [citation:3]
    DST_START_2026 = "2026-03-08"  # 8 de marzo
    DST_END_2026 = "2026-11-01"     # 1 de noviembre
    
    @classmethod
    def is_dst_active(cls, check_date=None):
        """Determina si el horario de verano está activo para una fecha"""
        if check_date is None:
            check_date = datetime.now(ZoneInfo('America/New_York'))
        
        dst_start = datetime.fromisoformat(f"{cls.DST_START_2026}").replace(tzinfo=ZoneInfo('America/New_York'))
        dst_end = datetime.fromisoformat(f"{cls.DST_END_2026}").replace(tzinfo=ZoneInfo('America/New_York'))
        
        return dst_start <= check_date < dst_end
    
    @classmethod
    def get_ny_tz_offset(cls, date=None):
        """Obtiene el offset horario de Nueva York para una fecha"""
        if date is None:
            date = datetime.now()
        
        ny_tz = ZoneInfo('America/New_York')
        ny_time = date.astimezone(ny_tz)
        # Retorna offset en horas respecto a UTC
        return ny_time.utcoffset().total_seconds() / 3600
    
    @classmethod
    def get_cet_offset(cls):
        """CET siempre es UTC+1 (estándar) o UTC+2 (verano)"""
        cet_tz = ZoneInfo('Europe/Madrid')
        cet_time = datetime.now().astimezone(cet_tz)
        return cet_time.utcoffset().total_seconds() / 3600
    
    @classmethod
    def get_market_hours_cet(cls, date=None):
        """Obtiene horas de apertura/cierre en CET para una fecha"""
        if date is None:
            date = datetime.now()
        
        # Parsear horas ET a datetime
        open_et = datetime.strptime(cls.MARKET_OPEN_ET, "%H:%M").time()
        close_et = datetime.strptime(cls.MARKET_CLOSE_ET, "%H:%M").time()
        
        # Crear datetime en ET para la fecha
        ny_tz = ZoneInfo('America/New_York')
        cet_tz = ZoneInfo('Europe/Madrid')
        
        open_dt_et = datetime.combine(date.date(), open_et).replace(tzinfo=ny_tz)
        close_dt_et = datetime.combine(date.date(), close_et).replace(tzinfo=ny_tz)
        
        # Convertir a CET
        open_dt_cet = open_dt_et.astimezone(cet_tz)
        close_dt_cet = close_dt_et.astimezone(cet_tz)
        
        return {
            'open_cet': open_dt_cet.strftime("%H:%M"),
            'close_cet': close_dt_cet.strftime("%H:%M"),
            'open_et': cls.MARKET_OPEN_ET,
            'close_et': cls.MARKET_CLOSE_ET,
            'dst_active': cls.is_dst_active(date)
        }