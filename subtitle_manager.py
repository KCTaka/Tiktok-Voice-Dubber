#!/usr/bin/env python3
"""
mkv-subtool.py - extract, edit, and re-mux subtitles in an MKV/MP4.
Requires: ffmpeg/ffprobe, pymkv, pysubs2.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from typing import List, Dict
from pymkv import MKVFile, MKVTrack     # pip install pymkv

# Map FFmpeg codec names -> filename extension
EXT_MAP = {"subrip": "srt", "srt": "srt",
           "ass": "ass", "ssa": "ass",
           "webvtt": "vtt", "vtt": "vtt"}

def run(cmd: List[str]) -> subprocess.CompletedProcess:
    """Run a command; raise on error, capture text output."""
    return subprocess.run(cmd, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def ffprobe_subs(path: Path) -> List[Dict]:
    """Return list of subtitle streams with index / codec / lang."""
    out = run([
        "ffprobe", "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index,codec_name:stream_tags=language",
        "-of", "json", str(path)
    ]).stdout
    return json.loads(out).get("streams", [])

def extract(path: Path, outdir: Path) -> List[Path]:
    """Extract **all** subtitle tracks; return list of files."""
    tracks = ffprobe_subs(path)
    if not tracks:
        print("⚠  No subtitle streams found."); return []
    out_files = []
    for t in tracks:
        idx, codec = t["index"], t["codec_name"]
        lang = t.get("tags", {}).get("language", "und")
        ext = EXT_MAP.get(codec, codec)
        outfile = outdir / f"{path.stem}_track{idx}_{lang}.{ext}"
        run(["ffmpeg", "-y", "-i", str(path),
             "-map", f"0:{idx}", "-c", "copy", str(outfile)])
        print(f"✓ extracted stream {idx} ({codec}, {lang}) -> {outfile.name}")
        out_files.append(outfile)
    return out_files

def mux(original: Path, sub_files: List[Path], output: Path):
    """Create new MKV: copy A/V, drop old subtitles, add sub_files."""
    if output.exists():
        raise FileExistsError(output)
    # Backup original just in case
    shutil.copy2(original, original.with_suffix(".bak.mkv"))
    mkv = MKVFile(str(original))
    for tr in list(mkv.tracks):
        if tr.track_type == "subtitles":
            mkv.remove_track(tr)
    for sub in sub_files:
        lang = sub.stem.split("_")[-1]  # crude lang guess
        mkv.add_track(MKVTrack(str(sub), language=lang))
    mkv.mux(str(output))
    print(f"★ New MKV written -> {output}")

def main():
    ap = argparse.ArgumentParser(description="Subtitle extractor/editor/remuxer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ext = sub.add_parser("extract", help="extract subtitle tracks")
    p_ext.add_argument("input", type=Path, help="input video (MKV/MP4)")
    p_ext.add_argument("-o", "--outdir", type=Path, default=Path("."))

    p_mux = sub.add_parser("mux", help="mux edited subtitle files back")
    p_mux.add_argument("input", type=Path, help="original video")
    p_mux.add_argument("subs", nargs="+", type=Path, help="edited .srt/.ass…")
    p_mux.add_argument("-o", "--output", type=Path, default=Path("output.mkv"))

    args = ap.parse_args()
    if args.cmd == "extract":
        extract(args.input, args.outdir)
    elif args.cmd == "mux":
        mux(args.input, args.subs, args.output)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.stderr)
