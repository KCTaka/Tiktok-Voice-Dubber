#!/usr/bin/env python3
"""
Turn an ASS subtitle file into a fully-timed TTS soundtrack.
usage: python tts_from_ass.py episode.ass out.mp3
"""
from __future__ import annotations
import io, sys
import pysubs2                                          # pip install pysubs2
from pydub import AudioSegment, effects                 # pip install pydub
from tqdm import tqdm                                   # pip install tqdm
import random
from tiktok_voice import tts_bytes, Voice

# ---------- 1. parse ASS ------------------------------------------------------
def load_events(path: str):
    subs = pysubs2.load(path)                           # auto-detect format
    for line in subs:
        if line.type != "Dialogue":                     # skip Comments etc.
            continue
        yield (
            int(line.start),                            # start-ms
            int(line.end),                              # end-ms
            (line.name or "NARRATOR").upper().strip(),  # speaker tag
            line.plaintext.replace("\\N", " ").strip() # Use line.plaintext here
        )

# ---------- 2. map speakers -> voices ----------------------------------------
DEFAULT_VOICES = list(Voice)

def get_characters(events):
    characters = set()
    for *_, speaker, _ in events:
        
        characters.add(speaker)
    return characters

def make_voice_map(events, predefined: dict[str, Voice] | None = None):
    mapping, pool_idx = dict(predefined or {}), 0
    for *_ , speaker, _ in events:
        if speaker not in mapping:
            mapping[speaker] = DEFAULT_VOICES[pool_idx % len(DEFAULT_VOICES)]
            pool_idx += 1
    return mapping

def make_unique_voice_map(events, predefined: dict[str, Voice] | None = None):
    """
    Assign a unique voice to each speaker from DEFAULT_VOICES without repetition.
    Raises an error if there are more speakers than available voices.
    """
    mapping = dict(predefined or {})
    assigned_voices = set(mapping.values())
    available_voices = [voice for voice in DEFAULT_VOICES if voice not in assigned_voices]

    # Extract unique speakers from events, excluding those already in mapping
    speakers = {speaker for *_, speaker, _ in events if speaker not in mapping}

    if len(speakers) > len(available_voices):
        raise ValueError("Not enough unique voices to assign to all speakers.")

    # Shuffle the available voices to ensure randomness
    random.shuffle(available_voices)

    for speaker, voice in zip(speakers, available_voices):
        mapping[speaker] = voice

    return mapping
    

# ---------- 3. synthesize each line -> AudioSegment ---------------------------
def synthesize(events, mapping):
    # Wrap events with tqdm for a progress bar
    for start_ms, end_ms, speaker, text in tqdm(events, desc="Synthesizing audio"):
        # Skip empty text lines which cause errors
        if not text:
            continue
        audio_bytes = tts_bytes(text, mapping[speaker])
        if not audio_bytes:                             # guard against failure
            print(f"Warning: Failed to synthesize line: {text[:50]}...") # Add a warning
            continue
        clip = AudioSegment.from_file(                  # read from memory
            io.BytesIO(audio_bytes), format="mp3"
        ).set_frame_rate(44100).set_channels(2)
        yield start_ms, clip                            # duration len(clip)

# ---------- 4. lay clips on a timeline & export ------------------------------
def assemble(clips, output_mp3: str):
    total_len = max((pos + len(seg) for pos, seg in clips), default=0) + 1000
    master = AudioSegment.silent(duration=total_len)    # :contentReference[oaicite:4]{index=4}
    for pos, seg in clips:
        master = master.overlay(seg, position=pos)      # precise alignment
    effects.normalize(master).export(output_mp3, format="mp3")
    print(f"✓ Wrote '{output_mp3}' ({master.duration_seconds:.1f}s)")

# ---------- 5. glue it together ------------------------------------------------
def main(ass_path, out_path="out.mp3"):
    raw_events = list(load_events(ass_path))
    voice_map   = make_voice_map(raw_events)
    clips       = list(synthesize(raw_events, voice_map))
    assemble(clips, out_path)

if __name__ == "__main__":
    # Use a raw string (prefix with r) to avoid backslash interpretation
    subtitle_file = r"Wajutsushi S01 1080p WEBRip DD+ x265-EMBER\subs\altered_ver.ass"
    output_file = "episode04_modern.mp3"
    raw_events = list(load_events(subtitle_file))
    characters_list = get_characters(raw_events)
    print(characters_list)
    voice_map = make_voice_map(raw_events)
    print(voice_map)
    voice_map = {'MAYOR DAVE': Voice.US_MALE_1, 
                 'NARRATOR': Voice.MALE_NARRATION, 
                 'JAKE': Voice.US_MALE_2, 
                 'SIGN': Voice.US_MALE_2, 
                 'EMILY': Voice.US_FEMALE_1, 
                 'SARAH': Voice.US_FEMALE_2,
                 }
    
    clips = list(synthesize(raw_events, voice_map))
    assemble(clips, output_file)
