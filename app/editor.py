import os
import random
from moviepy import VideoFileClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip, vfx
from moviepy.video.fx import Loop
from app.logger import get_logger

logger = get_logger(__name__)

def add_feedback_template(input_video_path, output_video_path, template_folder="templates/feedbacks", voices_folder="voices"):
    """
    Edits a video by resizing it, applying effects, overlaying a repeating feedback template,
    and adding a starting voice over the video.
    The template overlay starts 1 second into the video.
    The voice over is selected from the voices folder based on the video duration.
    
    For voice selection:
    - If the video duration is between N and N+1 seconds (e.g. if the video is between 12 and 13 seconds),
      the voice file "12s.mp3" is used.
    - If the corresponding voice file is not found, it falls back to "default.mp3".
    
    Args:
        input_video_path (str): Path to the input video.
        output_video_path (str): Path to save the edited output video.
        template_folder (str): Folder containing feedback templates.
        voices_folder (str): Folder containing voice audio files.
    
    Returns:
        str or None: Path to the edited video or None if an error occurs.
    """
    try:
        logger.info("Editing video: %s", input_video_path)

        # Load the original video
        original_clip = VideoFileClip(input_video_path)
        original_width, original_height = original_clip.size

        # Resize the original video to 90% of its size and center it
        zoomed_clip = original_clip.with_effects([vfx.Resize(0.9)]).with_position("center")
                
        # Find available templates
        templates = [
            os.path.join(template_folder, f)
            for f in os.listdir(template_folder)
            if f.lower().endswith((".mp4", ".mov", ".gif"))
        ]
        if not templates:
            logger.error("No template videos found in %s", template_folder)
            return None

        # Choose a random template
        template_path = random.choice(templates)
        logger.info("Selected feedback template: %s", template_path)

        # Load and resize the template clip to 20% of the original video's height
        template_clip = VideoFileClip(template_path)
        new_template_height = original_height * 0.20
        template_clip = template_clip.with_effects([vfx.Resize(height=new_template_height)])

        # Ensure template stays fully inside the frame (Top-Left)
        template_position = (0, 0)

        # Repeat the template so it plays throughout the entire video
        template_clip = template_clip.with_effects([Loop(duration=original_clip.duration)])

        # Apply effects: fade-in over 0.5s, slight zoom (1.2x), opacity adjustment,
        # and delay its appearance by 1 second using with_start().
        template_clip = (
            template_clip
            .with_effects([vfx.FadeIn(0.5)])
            .with_effects([vfx.Resize(1.2)])
            .with_opacity(0.90)
            .with_start(1)  # Template appears after 1 second
        )

        # Overlay the template on the resized clip
        composite_clip = CompositeVideoClip([
            zoomed_clip,
            template_clip.with_position(template_position)
        ]).with_duration(original_clip.duration)

        # Add starting voice over
        # Determine the appropriate voice file based on the video duration.
        # If the video duration is between N and N+1 seconds, use "Ns.mp3".
        voice_seconds = int(original_clip.duration)
        voice_filename = os.path.join(voices_folder, f"{voice_seconds}s.mp3")
        if not os.path.exists(voice_filename):
            logger.warning("Voice file %s not found, falling back to default.mp3", voice_filename)
            voice_filename = os.path.join(voices_folder, "default.mp3")
            if not os.path.exists(voice_filename):
                logger.error("Default voice file not found in %s", voices_folder)
                voice_audio = None
            else:
                voice_audio = AudioFileClip(voice_filename)
        else:
            voice_audio = AudioFileClip(voice_filename)
        
        # If voice audio is available, overlay it on the composite clip
        if voice_audio:
            # Combine the original audio (if any) with the voice audio starting at time 0
            if composite_clip.audio:
                combined_audio = CompositeAudioClip([composite_clip.audio, voice_audio.with_start(0)])
            else:
                combined_audio = voice_audio.with_start(0)
            composite_clip = composite_clip.with_audio(combined_audio)

        # Export final edited video
        composite_clip.write_videofile(output_video_path, codec="libx264", audio_codec="aac")
        logger.info("Video edited successfully: %s", output_video_path)
        return output_video_path

    except Exception as e:
        logger.exception("Error editing video: %s", e)
        return None
