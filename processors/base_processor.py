# processors/base_processor.py

from abc import ABC, abstractmethod
from typing import Dict, Any
from core.interfaces import EditManifest

class BaseProcessor(ABC):
    """
    Abstract Base Class for all Processors.
    
    Processors act as "Planners". They review the detection results and 
    update the EditManifest with instructions (filters, cuts, etc.).
    
    They do NOT modify the audio/video files directly.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize with the full configuration dictionary.
        """
        self.config = config

    @abstractmethod
    def process(self, manifest: EditManifest, host_audio, guest_audio, detection_results: Dict[str, Any]) -> EditManifest:
        """
        Logic to determine how the video/audio should be modified.
        
        Args:
            manifest: The current list of instructions (Edit Decision List).
            host_audio: Pydub AudioSegment (Reference only, do not modify).
            guest_audio: Pydub AudioSegment (Reference only, do not modify).
            detection_results: Dictionary of findings from the Detectors.
            
        Returns:
            The updated EditManifest.
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Return the unique name of this processor for logging.
        Example: 'AudioNormalizer'
        """
        pass

    def validate_config(self) -> bool:
        """
        Optional: Check if the required settings exist in self.config.
        Returns True by default.
        """
        return True