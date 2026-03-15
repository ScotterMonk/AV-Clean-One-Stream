# detectors/base_detector.py

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseDetector(ABC):
    """
    Abstract Base Class for all audio detectors in the single-stream workflow.
    Enforces the structure for Silence, Filler, and Spike detectors.
    """
    
    def __init__(self, config: Dict[str, Any]):
        # Modified by gpt-5.2 | 2026-01-20_01
        """
        Initialize with the full configuration dictionary.
        """
        self.config = config

    @abstractmethod
    def detect(self, audio) -> Any:
        # Modified by gpt-5.2 | 2026-01-20_01
        """
        Analyze audio and return detector-specific results.

        Most detectors return a list of (start_time, end_time) tuples in seconds.
        Some detectors may return structured dict-like analysis results.
        
        Args:
            audio: Pydub AudioSegment for the single audio track
            
        Returns:
            Detector-specific result.
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Return the unique name of this detector for logging/results.
        Example: 'cross_talk_detector'
        """
        pass
    
    def validate_config(self) -> bool:
        """
        Optional: Check if the required settings exist in self.config.
        Returns True by default. Override in subclasses if strict validation is needed.
        """
        return True
