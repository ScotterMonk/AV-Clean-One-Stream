# utils/time_helpers.py

import datetime

def seconds_to_hms(seconds: float) -> str:
    """
    Convert seconds to a standardized HH:MM:SS.mmm string.
    Useful for logging exact cut points.
    
    Args:
        seconds: Time in seconds (e.g., 65.5)
        
    Returns:
        String format "00:01:05.500"
    """
    if seconds < 0:
        return "00:00:00.000"
    
    # Create a timedelta object
    # We round microseconds to milliseconds for readability
    td = datetime.timedelta(seconds=seconds)
    
    # Get total seconds as integer
    total_seconds = int(td.total_seconds())
    
    # Calculate hours, minutes, seconds
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    
    # Get milliseconds
    millis = int(td.microseconds / 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

def format_duration(seconds: float) -> str:
    """
    Format a duration for user display.
    Shortens format if less than an hour.
    
    Examples: 
        65.5 -> "1m 05s"
        3665.0 -> "1h 01m 05s"
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
        
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {int(seconds):02d}s"
        
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes):02d}m {int(seconds):02d}s"

def parse_time_str(time_str: str) -> float:
    """
    Parse a time string (MM:SS or HH:MM:SS) into seconds.
    Useful if adding CLI args for specific start/end times.
    """
    parts = time_str.split(':')
    
    if len(parts) == 1:
        return float(parts[0])
    elif len(parts) == 2:
        # MM:SS
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        # HH:MM:SS
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    else:
        raise ValueError(f"Invalid time format: {time_str}")