# analyzers/audio_envelope.py

import numpy as np
from pydub import AudioSegment

def calculate_db_envelope(audio: AudioSegment, window_ms: int = 100) -> np.ndarray:
    """
    Calculates the dB (Loudness) envelope of an audio track.
    
    Uses NumPy vectorization for high performance on large files.
    
    Args:
        audio: Pydub AudioSegment
        window_ms: Size of the analysis window in milliseconds.
                Smaller = more precise timing, more noise.
                Larger = smoother, less precise timing.

    Returns:
        np.ndarray: Array of dB values, one per window.
    """
    # 1. Force Mono for envelope analysis
    # We just want to know "is there sound?", not "where is it?"
    if audio.channels > 1:
        audio = audio.set_channels(1)
        
    # 2. Extract raw samples
    # Convert to float32 for math precision
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    sample_rate = audio.frame_rate
    
    # 3. Calculate window size in samples
    window_size = int(sample_rate * window_ms / 1000)
    
    if window_size == 0:
        raise ValueError("Window size is too small for this sample rate")
        
    # 4. Handle padding
    # If total samples aren't perfectly divisible by window_size, 
    # we pad with silence (zeros) to ensure the reshape works.
    remainder = len(samples) % window_size
    if remainder != 0:
        padding = np.zeros(window_size - remainder, dtype=np.float32)
        samples = np.concatenate((samples, padding))
        
    # 5. Vectorized RMS Calculation
    # Reshape into 2D array: [Number of Windows, Samples per Window]
    # This allows us to calculate the mean of every window in one operation
    chunks = samples.reshape(-1, window_size)
    
    # Square -> Mean -> Sqrt
    rms_per_chunk = np.sqrt(np.mean(chunks**2, axis=1))
    
    # 6. Convert to dB
    # IMPORTANT: The amplitude reference must match the sample width.
    # - 16-bit PCM peak magnitude: 2^(16-1) = 32768
    # - 32-bit PCM peak magnitude: 2^(32-1)
    # If ref_value is too small, dB values are inflated and silence detection can fail.
    # We add a tiny epsilon (1e-9) to prevent log(0) errors on pure silence.
    sample_width = int(getattr(audio, "sample_width", 2) or 2)
    ref_value = float(1 << (8 * sample_width - 1))
    
    # Suppress divide by zero warnings for the log calculation
    with np.errstate(divide='ignore'):
        db_values = 20 * np.log10(rms_per_chunk / ref_value + 1e-9)
     
    return db_values
