# market_hours.py actualizado
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from market_hours_config import MarketHoursConfig

def is_trading_day(date=None):
    """Verifica si es un día de trading (lunes a viernes)"""
    if date is None:
        date = datetime.now(ZoneInfo('Europe/Madrid'))
    
    # 0 = lunes, 4 = viernes, 5 = sábado, 6 = domingo
    return date.weekday() < 5

def is_market_open(check_time=None):
    """
    Determina si el mercado está abierto en un momento dado (CET)
    Usa configuración dinámica de horarios
    """
    if check_time is None:
        check_time = datetime.now(ZoneInfo('Europe/Madrid'))

    if not is_trading_day(check_time):
        return False

    hours = MarketHoursConfig.get_market_hours_cet(check_time)
    open_time = datetime.strptime(hours['open_cet'], "%H:%M").time()
    close_time = datetime.strptime(hours['close_cet'], "%H:%M").time()

    current_time = check_time.time()
    return open_time <= current_time < close_time

def is_detector_active():
    """
    Determina si el detector debe estar activo ahora
    """
    return is_market_open()

def seconds_until_detector_active():
    """
    Calcula los segundos hasta que el detector deba activarse
    """
    now = datetime.now(ZoneInfo('Europe/Madrid'))
    
    if is_market_open(now):
        return 0
    
    # Buscar próxima apertura
    check_date = now.date()
    max_days = 7  # Evitar bucle infinito
    
    for _ in range(max_days):
        next_day = datetime.combine(check_date, time(0, 0)).replace(tzinfo=ZoneInfo('Europe/Madrid'))
        
        if not is_trading_day(next_day):
            check_date += timedelta(days=1)
            continue
            
        hours = MarketHoursConfig.get_market_hours_cet(next_day)
        open_time = datetime.strptime(hours['open_cet'], "%H:%M").time()
        next_open = datetime.combine(check_date, open_time).replace(tzinfo=ZoneInfo('Europe/Madrid'))
        
        if next_open > now:
            return (next_open - now).total_seconds()
            
        check_date += timedelta(days=1)
    
    return 24 * 3600  # Default 24h si no encuentra

def get_last_market_close(reference_time=None):
    """
    Obtiene el último cierre de mercado
    """
    if reference_time is None:
        reference_time = datetime.now(ZoneInfo('Europe/Madrid'))

    cursor = reference_time
    hours = MarketHoursConfig.get_market_hours_cet(cursor)
    close_time = datetime.strptime(hours['close_cet'], "%H:%M").time()

    cursor = cursor.replace(
        hour=close_time.hour,
        minute=close_time.minute,
        second=0,
        microsecond=0
    )

    if reference_time < cursor:
        cursor = cursor - timedelta(days=1)

    while not is_trading_day(cursor):
        cursor = cursor - timedelta(days=1)

    return cursor

