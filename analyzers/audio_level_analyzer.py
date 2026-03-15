# analyzers/audio_level_analyzer.py

import numpy as np
from pydub import AudioSegment
from utils.logger import get_logger

logger = get_logger(__name__)

# Try to import the industry-standard loudness library
try:
    import pyloudnorm as pyln
    HAS_PYLOUDNORM = True
except ImportError:
    HAS_PYLOUDNORM = False
    logger.warning("pyloudnorm not found. LUFS calculations will be approximated via RMS.")

def calculate_peak_db(audio: AudioSegment) -> float:
    """
    Returns the maximum peak level in dBFS.
    """
    return audio.max_dBFS

def calculate_rms_db(audio: AudioSegment) -> float:
    """
    Calculates the Root Mean Square (RMS) amplitude in dBFS.
    This represents the "average" physical energy.
    """
    # pydub's dBFS property uses RMS calculation internally
    return audio.dBFS

def calculate_lufs(audio: AudioSegment) -> float:
    """
    Calculates Integrated Loudness in LUFS (Loudness Units Full Scale).
    
    This is the broadcast standard (ITU-R BS.1770-4).
    It accounts for how the human ear perceives frequency loudness 
    (K-weighting) and ignores silence/quiet sections (Gating).
    """
    if not HAS_PYLOUDNORM:
        # Fallback: Estimate LUFS from RMS
        # RMS is usually 2-3dB lower than LUFS for speech, but varies wildly.
        # This is a rough approximation.
        return calculate_rms_db(audio)

    # 1. Prepare Data for pyloudnorm
    # Pyloudnorm expects a float numpy array of shape (samples, channels)
    # where values are normalized between -1.0 and 1.0
    
    # Get samples as int16/int32 based on sample width
    raw_data = np.array(audio.get_array_of_samples())
    
    # Normalize to float [-1.0, 1.0]
    # 16-bit audio = 2^15 = 32768
    # 24-bit audio = 2^23 = 8388608
    # 32-bit audio = 2^31 = 2147483648
    if audio.sample_width == 2:
        max_val = 32768.0
    elif audio.sample_width == 4:
        max_val = 2147483648.0
    else:
        # Fallback for weird formats (8-bit, 24-bit packed)
        max_val = float(2**(8 * audio.sample_width - 1))

    float_data = raw_data.astype(np.float32) / max_val

    # Handle Channels
    if audio.channels > 1:
        # Reshape to (samples, channels)
        # Pydub interleaves samples: [L, R, L, R...]
        float_data = float_data.reshape((-1, audio.channels))
    
    # 2. Measure Loudness
    try:
        meter = pyln.Meter(audio.frame_rate) # create BS.1770 meter
        loudness = meter.integrated_loudness(float_data)
        
        # Safety check for -inf (pure silence)
        if np.isinf(loudness):
            return -70.0 # Floor value
            
        return float(loudness)
        
    except Exception as e:
        logger.error(f"LUFS calculation failed: {e}")
        return calculate_rms_db(audio)