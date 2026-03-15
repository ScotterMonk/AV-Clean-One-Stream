# detectors/silence_detector.py

from .base_detector import BaseDetector
from analyzers.audio_envelope import calculate_db_envelope
import numpy as np
from typing import List, Tuple

class SilenceDetector(BaseDetector):
    """
    Detects silence in a single audio track.
    Used as building block for cross-talk detection.
    """
    
    def detect(self, host_audio, guest_audio) -> List[Tuple[float, float]]:
        """Detect silence in single track (not cross-talk aware)"""
        # This detector works on single tracks only
        # For demonstration, we'll analyze host audio
        audio = host_audio
        
        threshold_db = self.config.get('silence_threshold_db', -45)
        min_duration = self.config.get('min_silence_duration', 0.5)
        window_ms = self.config.get('silence_window_ms', 100)
        
        # Calculate dB envelope
        db_levels = calculate_db_envelope(audio, window_ms)
        
        # Find silent frames
        silent_frames = db_levels < threshold_db
        
        # Find continuous silent regions
        silent_regions = self._find_continuous_regions(
            silent_frames, 
            min_duration, 
            audio.frame_rate,
            window_ms
        )
        
        return silent_regions
    
    def _find_continuous_regions(self, mask, min_duration, sample_rate, window_ms):
        """Find continuous True regions in boolean mask"""
        regions = []
        start = None
        samples_per_window = int(sample_rate * window_ms / 1000)
        
        for i, is_silent in enumerate(mask):
            if is_silent and start is None:
                start = i
            elif not is_silent and start is not None:
                duration = (i - start) * window_ms / 1000
                if duration >= min_duration:
                    start_time = start * window_ms / 1000
                    end_time = i * window_ms / 1000
                    regions.append((start_time, end_time))
                start = None
        
        return regions
    
    def get_name(self) -> str:
        return "silence_detector"