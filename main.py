import os
import sys
import re
import shutil
from pathlib import Path

import ffmpeg
import pysubs2
from audio_separator.separator import Separator # pip install audio-separator
import logging

from tts_from_ass import *
from subtitle_manager import extract, mux

COLORS = {
    "green": "\033[92m",
    "red": "\033[91m",
    "blue": "\033[94m",
    "yellow": "\033[93m",
    "cyan": "\033[96m",
    "magenta": "\033[95m"
}

def print_colored(text: str, color: str, end: str = "\n") -> None:
    """ Print colored text."""
    color_code = COLORS.get(color.lower(), "\033[0m")
    colored_text = f"{color_code}{text}\033[0m"
    print(colored_text, end=end)

def input_colored(prompt: str, color: str) -> str:
    """ Get user input with colored prompt."""
    color_code = COLORS.get(color.lower(), "\033[0m")
    colored_prompt = f"{color_code}{prompt}\033[0m"
    return input(colored_prompt)

def get_milliseconds(time_str: str) -> int:
    """
    Convert a time string in the format hh:mm:ss[.ms], mm:ss[.ms], or ss[.ms] to milliseconds.
    """
    parts = time_str.strip().split(":")
    parts = [float(p) for p in parts]
    total_ms = 0

    if len(parts) == 3:
        hours, minutes, seconds = parts
        total_ms += int(hours * 3600000)
        total_ms += int(minutes * 60000)
        total_ms += int(seconds * 1000)
    elif len(parts) == 2:
        minutes, seconds = parts
        total_ms += int(minutes * 60000)
        total_ms += int(seconds * 1000)
    elif len(parts) == 1:
        seconds = parts[0]
        total_ms += int(seconds * 1000)
    else:
        raise ValueError(f"Invalid time format: {time_str}")

    return total_ms
    
def convert_ms(ms: int, time_depth: int = 2) -> str:
    full_seconds, ms = divmod(ms, 1000)
    full_minutes, seconds = divmod(full_seconds, 60)
    hours, minutes = divmod(full_minutes, 60)
    
    if time_depth == 1:
        return f"{full_seconds}.{ms:02d}"
    elif time_depth == 2:
        return f"{full_minutes:02d}:{seconds:02d}.{ms:02d}"
    elif time_depth == 3:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:02d}"
    
    raise ValueError(f"Invalid time depth: {time_depth}")

def parse_line(line):
    # Define the regex pattern to match the formatted string: start_ms | end_ms | name | text
    pattern = r'^(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(.+)$'

    # Use regex to find matches
    match = re.match(pattern, line)

    if match:
        start_ms, end_ms, name, text = match.groups()
        start = int(start_ms.strip()) # Convert to int
        end = int(end_ms.strip())   # Convert to int
        name = name.strip()
        text = text.strip()
        return start, end, name, text
    else:
        # Optionally print the line that failed to parse for debugging
        # print_colored(f"Failed to parse line: {line}", "red")
        raise ValueError("Line format is incorrect. Expected: 'start_ms | end_ms | name | text'")

def get_output_dir(video_file: str, out_dir: str) -> str:
    """ Generate output dir name based on the video file name. Will incrementally increase if the file already exists."""
    video_name = os.path.splitext(os.path.basename(video_file))[0]
    video_name = re.sub(r'[^a-zA-Z0-9]', '_', video_name)  # Replace non-alphanumeric characters with underscores
    out_dir = os.path.join(out_dir, video_name)
    
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
        return out_dir
    
    i = 1
    while os.path.exists(out_dir + f"_{i}"):
        i += 1
    out_dir = out_dir + f"_{i}"
    os.makedirs(out_dir)
    return out_dir

def get_subtitles(video_file: str, out_dir: str = "subtitles/") -> str:
    """ 
        Extract subtitles from the video file to out_dir.
        Selects the best subtitle track (preferring English ASS/SRT).
        Returns the path to the selected subtitle file.
    """
    video_path = Path(video_file)
    output_path = Path(out_dir)
    output_path.mkdir(parents=True, exist_ok=True) # Ensure output dir exists

    try:
        extracted_files = extract(video_path, output_path)
    except Exception as e:
        print_colored(f"Error extracting subtitles: {e}", "red")
        raise

    if not extracted_files:
        raise FileNotFoundError(f"No subtitle tracks found in {video_file}")

    # Selection logic: Prioritize English ASS, then English SRT, then any ASS, then any SRT, then first file
    selected_file = None
    priorities = [
        lambda p: p.suffix == ".ass" and "eng" in p.stem.lower(),
        lambda p: p.suffix == ".srt" and "eng" in p.stem.lower(),
        lambda p: p.suffix == ".ass",
        lambda p: p.suffix == ".srt",
    ]

    for priority_check in priorities:
        for f in extracted_files:
            if priority_check(f):
                selected_file = f
                break
        if selected_file:
            break

    # Fallback to the first extracted file if no priority match
    if not selected_file:
        selected_file = extracted_files[0]

    print_colored(f"Selected subtitle file: {selected_file.name}", "green")
    return str(selected_file)

def mux_subtitles(video_file: str, sub_file: str, out_dir: str):
    """ Codec adds subtitle to MKV file. Uses subtitle_manager.py mux """
    output_filename = os.path.join(out_dir, f"subtitle_{os.path.splitext(os.path.basename(video_file))[0]}.mkv")
    
    try:
        print_colored(f"Muxing subtitles into {output_filename}...", "yellow")
        mux(video_file, [sub_file], output_filename) # Mux with the selected subtitle file
        print_colored(f"Subtitles muxed successfully to {output_filename}", "green")
    except Exception as e:
        print_colored(f"Error muxing subtitles: {e}", "red")
        raise

def clip_video(video_file: str, clip_start: int, clip_end: int, out_dir: str) -> str:
    """" Clip the video file from clip_start (ms) to clip_end (ms). """
    output_filename = os.path.join(out_dir, "clip_" + os.path.basename(video_file))
    start_seconds = clip_start / 1000.0
    duration_seconds = (clip_end - clip_start) / 1000.0

    try:
        print_colored(f"Clipping video from {start_seconds:.2f}s for {duration_seconds:.2f}s...", "yellow")
        (
            ffmpeg
            .input(video_file, ss=start_seconds)
            .output(output_filename,
                    t=duration_seconds,
                    vcodec='libx264',    # re-encode video
                    acodec='aac',        # re-encode audio
                    preset='fast',       # optional: encoding speed
                    crf=23,              # optional: visual quality
                    avoid_negative_ts='make_zero')
            .run(overwrite_output=True, quiet=True)
        )
        print_colored(f"Video clipped successfully to {output_filename}", "green")
        # Verify the actual start time if possible/needed using ffprobe, though difficult with copy
        return output_filename
    except ffmpeg.Error as e:
        stderr_output = e.stderr.decode() if e.stderr else "No stderr output."
        print_colored(f"Error clipping video: {stderr_output}", "red")
        raise

def clip_subtitles(sub_file: str, clip_start: int, clip_end: int, out_dir: str) -> str:
    """ 
        Copy and Clip the subtitle file from clip_start (ms) to clip_end (ms).
        Adjusts timestamps relative to the clip start time (0).
    """
    clip_sub_file = os.path.join(out_dir, "clip_" + os.path.basename(sub_file))

    try:
        # Load subtitles, explicitly using UTF-8
        subs = pysubs2.load(sub_file, encoding="utf-8")
        clip_duration = clip_end - clip_start
        clip_events = []

        for event in subs.events:
            # Skip events completely outside the clip range
            if event.end <= clip_start or event.start >= clip_end:
                continue

            # Adjust start and end times relative to the clip's start time (0)
            new_start = max(0, event.start - clip_start)
            new_end = min(clip_duration, event.end - clip_start) # Ensure end doesn't exceed clip duration

            # Ensure duration is positive and start is before end
            if new_end > new_start:
                event.start = new_start
                event.end = new_end
                clip_events.append(event)

        subs.events = clip_events
        # Save clipped subtitles, preserving original format for now
        subs.save(clip_sub_file, encoding="utf-8")
        print_colored(f"Subtitles clipped successfully to {clip_sub_file}", "green")
        return clip_sub_file
    except Exception as e:
        print_colored(f"Error clipping subtitles: {e}", "red")
        raise


def edit_subtitles(sub_file: str, out_dir: str) -> str:
    """ User edits the subtitle file via a temporary txt file.
        Saves the edited subtitles in ASS format.
        Returns the path to the edited ASS subtitle file.
    """
    # Ensure the output file has .ass extension for TTS compatibility
    base_name = os.path.splitext(os.path.basename(sub_file))[0]
    edited_sub_file = os.path.join(out_dir, f"edited_{base_name}.ass")
    temp_txt_file = os.path.join(out_dir, "subtitles_to_edit.txt")

    try:
        # 1. Load the clipped subtitles
        subs = pysubs2.load(sub_file, encoding="utf-8")
        # Store original styles and info if needed later, though ASS saving handles styles
        original_styles = subs.styles
        original_info = subs.info

        # 2. Convert to readable format (start_ms | end_ms | name | text) and write to txt
        print_colored(f"Writing subtitles to {temp_txt_file} for editing...", "yellow")
        with open(temp_txt_file, "w", encoding="utf-8") as f:
            f.write("# Format: start_milliseconds | end_milliseconds | character_name | text\n")
            f.write("# -------------------- DIALOGUES --------------------\n")
            for event in subs.events:
                # Write start/end times as integers (milliseconds)
                f.write(f"{event.start} | {event.end} | {event.name} | {event.text}\n")

        # 3. Wait for user to edit the subtitles.
        print_colored(f"Please edit the subtitles in '{temp_txt_file}'", "cyan")
        input_colored("Press Enter after saving your changes to continue...", "cyan")

        # 4. Read the edited subtitles from the txt file
        print_colored(f"Reading edited subtitles from {temp_txt_file}...", "yellow")
        with open(temp_txt_file, "r", encoding="utf-8") as f:
            edited_lines = f.readlines()

        edited_events = []
        line_num = 0
        for line in edited_lines:
            line_num += 1
            line = line.strip()
            if not line or line.startswith("#"): # Skip empty lines and comments
                continue
            try:
                start, end, name, text = parse_line(line) # Use updated parse_line
                # Re-create SSAEvent, preserving original style if possible
                # Note: pysubs2 automatically assigns 'Default' if name is not in styles
                # We might need more sophisticated style handling if complex edits are expected
                edited_events.append(pysubs2.SSAEvent(
                    start=start,
                    end=end,
                    name=name,
                    text=text,
                    # style=original_style_name # This requires mapping name back to style, complex
                ))
            except ValueError as e:
                print_colored(f"Skipping invalid line {line_num} in {temp_txt_file}: {e}", "red")
                continue

        # Create a new SSAFile to save, preserving original info/styles
        edited_subs = pysubs2.SSAFile()
        edited_subs.info = original_info
        edited_subs.styles = original_styles # Copy original styles
        edited_subs.events = edited_events

        # 5. Save the edited subtitles to the final ASS file.
        edited_subs.save(edited_sub_file, format_="ass", encoding="utf-8") # Explicitly save as ASS
        print_colored(f"Edited subtitles saved to {edited_sub_file}", "green")
        
        
        # Optionally remove the temporary text file
        # os.remove(temp_txt_file)
        return edited_sub_file
    except Exception as e:
        print_colored(f"Error editing subtitles: {e}", "red")
        raise


def get_audio(video_file: str, out_dir: str) -> str:
    """ Extract audio from the video file to out_dir. Returns the path to the audio file."""
    audio_filename = os.path.join(out_dir, "audio_" + os.path.splitext(os.path.basename(video_file))[0] + ".mp3") # Output as mp3
    try:
        print_colored(f"Extracting audio from {video_file}...", "yellow")
        (
            ffmpeg
            .input(video_file)
            .output(audio_filename, acodec='mp3', vn=None) # Specify mp3 codec, vn=None removes video
            .run(overwrite_output=True, quiet=True)
        )
        print_colored(f"Audio extracted successfully to {audio_filename}", "green")
        return audio_filename
    except ffmpeg.Error as e:
        print_colored(f"Error extracting audio: {e.stderr.decode()}", "red")
        raise


def remove_vocal(audio_file: str, out_dir: str) -> str:
    """ 
        Remove vocal from the audio file using audio-separator.
        Returns the path to the background (instrumental) audio file.
    """
    # Define the expected output path for the background audio
    # audio-separator might output wav/flac, let's assume wav for now and handle rename
    base_name = os.path.splitext(os.path.basename(audio_file))[0]
    # Ensure bg_audio_final_path uses the correct out_dir
    bg_audio_final_path = os.path.join(out_dir, f"bg_{base_name}.wav") # Desired final path

    try:
        print_colored(f"Separating vocals from {audio_file}...", "yellow")
        separator = Separator(output_dir=out_dir, log_level=logging.INFO) 

        model_name = 'UVR-MDX-NET-Inst_HQ_3.onnx'
        separator.load_model(model_filename=model_name)

        # Perform separation - assume output_files contains filenames or relative paths
        output_files = separator.separate(audio_file)

        # Find the instrumental *filename*
        instrumental_filename = None
        for f in output_files:
            # Check the basename in case the returned paths are relative/absolute but inconsistent
            fname_check = os.path.basename(f)
            if "(Instrumental)" in fname_check:
                instrumental_filename = fname_check # Store only the filename
                break

        if not instrumental_filename:
            raise FileNotFoundError(f"Instrumental track filename not found in separation output for {audio_file}")

        # Construct the full path *within the output directory*
        instrumental_path = os.path.join(out_dir, instrumental_filename)

        # Check if the constructed path actually exists before trying to move
        if not os.path.exists(instrumental_path):
             raise FileNotFoundError(f"Constructed instrumental path does not exist: {instrumental_path}")

        print_colored(f"Found instrumental track: {instrumental_path}", "green") # Log the full path

        # Rename the instrumental file to the desired final path
        if os.path.exists(bg_audio_final_path):
             os.remove(bg_audio_final_path) 
        shutil.move(instrumental_path, bg_audio_final_path)
        print_colored(f"Background audio saved to {bg_audio_final_path}", "green")

        # Clean up the other separated file (vocals) using the filename
        for f in output_files:
            fname_check = os.path.basename(f) # Get basename for comparison
            if fname_check != instrumental_filename:
                 # Construct full path for removal
                 full_path_to_remove = os.path.join(out_dir, fname_check)
                 if os.path.exists(full_path_to_remove):
                     try:
                         os.remove(full_path_to_remove)
                         print_colored(f"Removed temporary file: {full_path_to_remove}", "yellow")
                     except OSError as e:
                         print_colored(f"Could not remove temporary separated file {full_path_to_remove}: {e}", "yellow")

        return bg_audio_final_path

    except Exception as e:
        print_colored(f"Error removing vocals: {e}", "red")
        # Optionally print traceback for more detail during debugging
        # import traceback
        # traceback.print_exc()
        raise


def get_tts(sub_file: str, out_dir: str) -> str:
    """ 
        Generate TTS audio from the ASS subtitle file and save it to out_dir.
        Returns the path to the TTS audio file.
    """
    # Ensure subfile in ASS format
    if not sub_file.lower().endswith('.ass'): # Check lower case
        raise ValueError("The subtitle file must be in ASS format for TTS generation.")

    # TTS Audio name
    tts_audio_file = os.path.join(out_dir, "tts_" + os.path.splitext(os.path.basename(sub_file))[0] + ".mp3")

    try:
        print_colored(f"Generating TTS from {sub_file}...", "yellow")
        # Load ASS events using the function from tts_from_ass
        raw_events = list(load_events(sub_file)) # Assuming load_events handles pysubs2 internally or expects path

        if not raw_events:
             print_colored("No events found in subtitle file for TTS.", "yellow")
             # Create an empty mp3 file? Or handle downstream? Let's return expected path but empty.
             # This requires creating a silent mp3. For now, raise error.
             raise ValueError(f"No dialogue events found in {sub_file} to synthesize.")


        # Display character with index
        print_colored("=========CHARACTERS=========", "cyan")
        characters_list = get_characters(raw_events) # Assuming get_characters works with loaded events
        if not characters_list:
             raise ValueError(f"No characters found in {sub_file}.")

        for index, character in enumerate(characters_list):
            print_colored(f"{index}: {character}", "green")

        # Display voices with index
        print_colored("=========VOICES=========", "cyan")
        # Assuming DEFAULT_VOICES is defined in tts_from_ass
        available_voices = DEFAULT_VOICES
        voice_name_map = {str(i): v for i, v in enumerate(available_voices)} # Map index string to voice object
        for index, voice in enumerate(available_voices):
            print_colored(f"{index}: {voice.name}", "green") # Assuming voice object has a .name attribute

        print_colored("Map characters to voices - Enter index number.", "cyan")
        print_colored("Leave blank or enter invalid index to assign randomly later.", "cyan")

        # Let user select voices
        voice_map_input = {}
        for character in characters_list:
            # Use input_colored for prompts
            voice_choice_idx = input_colored(f"Choose voice index for '{character}' (default: random): ", "magenta")
            if voice_choice_idx in voice_name_map:
                voice_map_input[character] = voice_name_map[voice_choice_idx] # Map character to voice object
            else:
                 print_colored(f"No specific voice selected for '{character}', will assign randomly if needed.", "yellow")


        # Assign voices using make_unique_voice_map from tts_from_ass
        # This function should handle assigning random voices to unmapped characters
        # It should return a map of {character_name: voice_object}
        final_voice_map = make_unique_voice_map(raw_events, voice_map_input) # Pass available voices

        print_colored("=========FINAL VOICE MAP=========", "cyan")
        for char, voice in final_voice_map.items():
             print_colored(f"{char}: {voice.name}", "green")


        # Synthesize audio clips
        print_colored("Synthesizing audio clips...", "yellow")
        # Assuming synthesize yields tuples like (start_ms, end_ms, audio_segment)
        audio_clips = list(synthesize(raw_events, final_voice_map))

        if not audio_clips:
             raise ValueError("TTS synthesis produced no audio clips.")


        # Assemble audio clips into a single file
        print_colored(f"Assembling TTS audio to {tts_audio_file}...", "yellow")
        # Assuming assemble takes the clips and output path
        assemble(audio_clips, tts_audio_file)

        print_colored(f"TTS audio generated successfully: {tts_audio_file}", "green")
        return tts_audio_file

    except Exception as e:
        print_colored(f"Error generating TTS: {e}", "red")
        raise


def combine_video_audio_mixed(video_file: str, *audio_files: str, out_dir: str = "") -> str:
    """
    Combine video (no audio) and multiple audio files into a single
    output file with the first two audio sources mixed into one track using amix.
    Assumes the first audio file is primary (e.g., TTS) and the second is background.
    Saves to out_dir. Returns the path to the output video file.
    """
    # Basic validation
    if len(audio_files) < 1:
        raise ValueError("At least one audio file must be provided to combine.")
    if len(audio_files) > 2:
        print_colored(f"Warning: Received {len(audio_files)} audio files. Mixing logic currently combines only the first two.", "yellow")

    base_name = os.path.splitext(os.path.basename(video_file))[0]
    if base_name.startswith("clip_"):
        base_name = base_name[len("clip_"):]
    final_clip_file = os.path.join(out_dir, f"final_{base_name}.mkv")

    try:
        print_colored(f"Combining video and {len(audio_files)} audio track(s) into {final_clip_file}...", "yellow")

        # --- Define Inputs ---
        in_video = ffmpeg.input(video_file)
        audio_inputs = [ffmpeg.input(f) for f in audio_files]

        # --- Prepare Output Streams ---
        video_stream = in_video['v'] # Select video stream explicitly
        final_audio_stream = None

        if len(audio_inputs) == 1:
            # Only one audio file, use it directly
            print_colored("Only one audio file provided, no mixing required.", "cyan")
            # Select the first audio stream explicitly
            final_audio_stream = audio_inputs[0]['a:0'] # Directly select the first audio stream
        elif len(audio_inputs) >= 2:
            # Mix the first two audio files
            print_colored("Mixing first two audio files (TTS and Background)...", "cyan")
            # Select the first audio stream from each input explicitly
            tts_stream = audio_inputs[0]['a:0'] # Directly select the first audio stream
            bg_stream = audio_inputs[1]['a:0']  # Directly select the first audio stream

            # Apply volume adjustment to background and mix
            # Note: Using tts_stream directly assumes volume=1.0
            bg_vol = ffmpeg.filter(bg_stream, 'volume', 1)
            final_audio_stream = ffmpeg.filter([tts_stream, bg_vol], 'amix', inputs=2)

        if final_audio_stream is None:
             raise RuntimeError("Could not determine final audio stream.") # Should not happen with checks above

        # --- Create and Run FFmpeg Command using ffmpeg-python chaining ---
        # Pass the selected video stream and the final audio stream (single or mixed)
        # ffmpeg-python handles the mapping automatically based on the order of streams passed
        process = ffmpeg.output(
            video_stream,        # Input video stream
            final_audio_stream,  # Input audio stream (either single or mixed)
            final_clip_file,
            vcodec='copy',       # Copy video stream
            acodec='aac',        # Encode the final audio to AAC (safe choice)
            shortest=None        # Use longest duration (default). Use True for shortest.
            # No explicit map or filter_complex needed here
        )

        # Run the process (set quiet=False for debugging FFmpeg command/output)
        process.run(overwrite_output=True, quiet=True)

        print_colored(f"Final video with mixed audio created successfully: {final_clip_file}", "green")
        return final_clip_file

    except ffmpeg.Error as e:
        stderr_output = e.stderr.decode() if e.stderr else "No stderr output."
        print_colored(f"Error combining/mixing video and audio: {stderr_output}", "red")
        raise
    except Exception as e: # Catch other non-ffmpeg errors
         print_colored(f"An unexpected error occurred during combination/mixing: {e}", "red")
         # import traceback
         # traceback.print_exc() # Uncomment for detailed debugging
         raise

def main():
    # --- User Configuration ---
    video_file = "videos/video.mkv" # Example video
    clip_start_time_str = "09:35" # Example start time (mm:ss or hh:mm:ss.ms etc) - Corrected format
    clip_end_time_str = "10:30"   # Example end time - Corrected format
    base_output_folder = "clips/" # Base folder for all generated clips
    # --- End Configuration ---

    try:
        # Validate video file exists
        if not os.path.exists(video_file):
            print_colored(f"Video file not found: {video_file}", "red")
            sys.exit(1)

        # Convert times to milliseconds
        clip_start_ms = get_milliseconds(clip_start_time_str)
        clip_end_ms = get_milliseconds(clip_end_time_str)
        if clip_end_ms <= clip_start_ms:
             print_colored("Error: Clip end time must be after start time.", "red")
             sys.exit(1)


        print_colored(f"Processing video: {video_file}", "blue")
        print_colored(f"Clip range: {clip_start_time_str} ({clip_start_ms}ms) to {clip_end_time_str} ({clip_end_ms}ms)", "blue")

        # 1. Extract Subtitles (to a general subtitles folder)
        subtitle_folder = "subtitles/"
        sub_file = get_subtitles(video_file, subtitle_folder)

        # 2. Determine unique output directory for this run
        # IMPORTANT: Define out_dir *before* the try block so it's available in except blocks
        out_dir = get_output_dir(video_file, base_output_folder)
        print_colored(f"Output directory: {out_dir}", "blue")

        # --- Start of process that might fail ---
        try:
            # 3. Clip Video
            clip_file = clip_video(video_file, clip_start_ms, clip_end_ms, out_dir)

            # 4. Clip Subtitles
            clip_sub_file = clip_subtitles(sub_file, clip_start_ms, clip_end_ms, out_dir)

            # 5. Edit Subtitles (User interaction)
            edited_sub_file = edit_subtitles(clip_sub_file, out_dir)

            # 6. Generate TTS from Edited Subtitles
            if not os.path.exists(edited_sub_file) or not edited_sub_file.lower().endswith('.ass'):
                 print_colored(f"Edited subtitle file ({edited_sub_file}) not found or not in ASS format. Cannot generate TTS.", "red")
                 raise FileNotFoundError(f"Edited subtitle file not found or invalid: {edited_sub_file}") # Raise error to trigger cleanup
            tts_audio_file = get_tts(edited_sub_file, out_dir)

            # 7. Extract Audio from Clipped Video
            audio_file = get_audio(clip_file, out_dir)

            # 8. Remove Vocals / Get Background Audio
            bg_audio_file = remove_vocal(audio_file, out_dir)

            # 9. Combine Video (no audio) + TTS Audio + Background Audio
            # Ensure both audio files exist before combining
            if not os.path.exists(tts_audio_file):
                raise FileNotFoundError(f"TTS audio file not found: {tts_audio_file}")
            if not os.path.exists(bg_audio_file):
                raise FileNotFoundError(f"Background audio file not found: {bg_audio_file}")

            final_clip_file_no_subs = combine_video_audio_mixed(clip_file, tts_audio_file, bg_audio_file, out_dir=out_dir)

            # 10. Add subtitles to the combined video
            # # Make sure the combined video exists before muxing
            # if not os.path.exists(final_clip_file_no_subs):
            #      raise FileNotFoundError(f"Combined video file not found after mixing: {final_clip_file_no_subs}")
            # # Define final output name *after* muxing
            # final_output_video = os.path.join(out_dir, f"final_subtitled_{os.path.splitext(os.path.basename(final_clip_file_no_subs))[0]}.mkv")
            # mux_subtitles(final_clip_file_no_subs, edited_sub_file, final_output_video) # Pass specific output path

            # Optional: Remove the intermediate combined file without subs if desired
            # os.remove(final_clip_file_no_subs)

            print_colored("\nProcessing complete!", "magenta")
            # print_colored(f"Final output video with subtitles: {final_output_video}", "magenta") # Print the final muxed file path

        except FileNotFoundError as e:
            print_colored(f"\nError: Required file not found - {e}", "red")
            print_colored(f"Cleaning up output directory: {out_dir}", "yellow")
            shutil.rmtree(out_dir, ignore_errors=True) # Clean up on error
            sys.exit(1)
        except ValueError as e:
            print_colored(f"\nError: Invalid value or format - {e}", "red")
            print_colored(f"Cleaning up output directory: {out_dir}", "yellow")
            shutil.rmtree(out_dir, ignore_errors=True) # Clean up on error
            sys.exit(1)
        except ffmpeg.Error as e:
            print_colored(f"\nError: FFmpeg processing failed.", "red")
            if hasattr(e, 'stderr') and e.stderr:
                 # Limit printing potentially long stderr
                 stderr_head = e.stderr.decode().splitlines()[:20] # First 20 lines
                 print_colored("FFmpeg Error Output (partial):\n" + "\n".join(stderr_head), "red")
            else:
                 print_colored(f"FFmpeg Error: {e}", "red")
            print_colored(f"Cleaning up output directory: {out_dir}", "yellow")
            shutil.rmtree(out_dir, ignore_errors=True) # Clean up on error
            sys.exit(1)
        except Exception as e: # Catch other potential errors
            print_colored(f"\nAn unexpected error occurred: {e}", "red")
            import traceback
            traceback.print_exc() # Print detailed traceback for debugging
            print_colored(f"Cleaning up output directory: {out_dir}", "yellow")
            shutil.rmtree(out_dir, ignore_errors=True) # Clean up on error
            sys.exit(1)

    # --- This outer try-except handles errors *before* out_dir is created or KeyboardInterrupt ---
    except KeyboardInterrupt: # Keep KeyboardInterrupt separate for graceful exit message
        print_colored("\nExiting gracefully...", "yellow")
        # Decide if cleanup is needed for KeyboardInterrupt - currently no cleanup
        sys.exit(0)
    except Exception as e: # Catch errors like initial file not found, bad time format etc.
        print_colored(f"\nAn initial setup error occurred: {e}", "red")
        # No out_dir cleanup needed here as it likely wasn't created yet
        sys.exit(1)


if __name__ == "__main__":
    main()