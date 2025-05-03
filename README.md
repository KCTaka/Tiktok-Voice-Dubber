# Video Clip Processing Pipeline

This project provides a Python script (`main.py`) to automate a video processing pipeline. It allows users to clip a section of a video, extract and edit its subtitles, generate Text-to-Speech (TTS) audio for the edited dialogue, separate background music from the original clip's audio, and finally combine the clipped video (without its original audio) with the generated TTS and background audio tracks.

## Features

*   **Video Clipping:** Extracts a specific time segment from a source video file.
*   **Subtitle Extraction:** Extracts subtitle tracks from the source video (prioritizes English ASS/SRT).
*   **Subtitle Clipping:** Clips the extracted subtitles to match the video clip's duration and adjusts timestamps.
*   **Subtitle Editing:** Facilitates manual editing of clipped subtitles via a temporary text file.
*   **TTS Generation:** Generates TTS audio (MP3) from the edited ASS subtitles using character voices.
*   **Audio Extraction:** Extracts the original audio from the clipped video segment.
*   **Vocal Removal:** Separates vocals from the extracted audio to isolate background music/effects (using `audio-separator`).
*   **Audio Mixing:** Combines the generated TTS audio and the background audio into a single track.
*   **Final Video Combination:** Muxes the clipped video (video stream only) with the mixed audio track.
*   **Subtitle Muxing:** Adds the edited subtitles back into the final video.

## Setup

1.  **Install FFmpeg:** This project relies heavily on FFmpeg. Ensure it is installed on your system and accessible in your PATH. You can download it from [ffmpeg.org](https://ffmpeg.org/download.html).
2.  **Install Python Dependencies:** Install the required Python packages using pip:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: `audio-separator` might have additional dependencies like `onnxruntime`. Refer to its documentation for complete installation if you encounter issues.*
3.  **Configure Models (if necessary):**
    *   `audio-separator`: Ensure the required model file (e.g., `UVR-MDX-NET-Inst_HQ_3.onnx`) is available or downloaded by the library.
    *   `tts_from_ass.py`: Ensure any required voice models or configurations for the TTS engine are set up.

## Usage

1.  **Configure `main.py`:**
    *   Set the `video_file` variable to the path of your source video.
    *   Set `clip_start_time_str` and `clip_end_time_str` to define the desired clip segment (format: "MM:SS" or "HH:MM:SS.ms").
    *   Set `base_output_folder` to specify the directory where output subfolders will be created.
2.  **Run the Script:**
    ```bash
    python main.py
    ```
3.  **Follow Prompts:**
    *   The script will pause for subtitle editing. Open the generated `.txt` file (e.g., `clips/your_video_name/subtitles_to_edit.txt`), make your changes, save the file, and press Enter in the console.
    *   The script will prompt you to map characters found in the subtitles to available TTS voices. Enter the corresponding index number for each character.
4.  **Output:** The final processed video (with mixed audio and edited subtitles) will be saved in a uniquely named subfolder within your specified `base_output_folder`. Intermediate files (clipped video, audio tracks, subtitles) are also kept in this folder.

## Core Libraries

*   [ffmpeg-python](https://github.com/kkroening/ffmpeg-python): Python bindings for FFmpeg.
*   [pysubs2](https://github.com/tkarabela/pysubs2): Library for editing subtitle files.
*   [audio-separator](https://github.com/karaokenerds/python-audio-separator): Library for separating audio sources (vocals, background).
*   [tiktok-voice](https://github.com/mark-rez/TikTok-Voice-TTS): Used for TTS generation via `tts_from_ass.py`.
*   [pydub](https://github.com/jiaaro/pydub): Used for audio manipulation in `tts_from_ass.py`.
*   [tqdm](https://github.com/tqdm/tqdm): Used for progress bars.
