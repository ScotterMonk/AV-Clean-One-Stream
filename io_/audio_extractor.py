# io/audio_extractor.py

import os
import tempfile
import ffmpeg
from pydub import AudioSegment
from utils.logger import get_logger

logger = get_logger(__name__)

def extract_audio(video_path: str, target_sr: int = 44100) -> AudioSegment:
    """
    Extracts audio from a video file to a pydub AudioSegment.
    
    It creates a temporary WAV file to ensure clean decoding and 
    standardized sample rate before analysis.
    
    Args:
        video_path: Path to the source video file
        target_sr: Sample rate to standardize on (default 44100)
        
    Returns:
        pydub.AudioSegment: The audio data ready for analysis
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    logger.info(f"Extracting audio from: {os.path.basename(video_path)}")

    # Create a temporary file for the extracted audio
    # We use a named temporary file that persists until we manually delete it
    fd, temp_path = tempfile.mkstemp(suffix='.wav')
    os.close(fd) # Close the file descriptor immediately, we just wanted the path

    try:
        # Run FFmpeg to extract audio
        # - vn: No video
        # - ac: 2 channels (Stereo) - Essential for consistent LUFS calc
        # - ar: Sample rate (44100) - Essential for aligning arrays in detectors
        # - y: Overwrite output
        (
            ffmpeg
            .input(video_path)
            .output(temp_path, ac=2, ar=target_sr, vn=None, f='wav', loglevel='error')
            .run(overwrite_output=True)
        )

        # Load into pydub
        # This puts the audio into RAM. 
        # Note: A 1-hour stereo 16-bit WAV is ~600MB. 
        # If processing huge files on low RAM, we would need a streaming approach,
        # but for most podcast/YouTube workflows, this is fastest.
        audio_segment = AudioSegment.from_wav(temp_path)
        
        logger.debug(f"Audio loaded: {audio_segment.duration_seconds:.2f}s, {audio_segment.frame_rate}Hz")
        
        return audio_segment

    except ffmpeg.Error as e:
        logger.error("FFmpeg failed to extract audio")
        # Try to read stderr if available
        if hasattr(e, 'stderr') and e.stderr:
            logger.error(e.stderr.decode('utf8'))
        raise RuntimeError(f"Could not extract audio from {video_path}") from e

    finally:
        # Cleanup: Remove the temporary WAV file
        if os.path.exists(temp_path):
            os.remove(temp_path)
            logger.debug("Cleaned up temporary audio file")