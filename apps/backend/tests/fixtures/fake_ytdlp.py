"""Stand-in for the yt-dlp executable in tests (run as: python fake_ytdlp.py <yt-dlp args>).

FAKE_YTDLP_MODE: ok (default) | private | slow | nosubs
FAKE_YTDLP_WAV: audio file to "download"
FAKE_YTDLP_LOG: append the received args and ELECTRON_RUN_AS_NODE here (JSON lines)
"""
import json
import os
import shutil
import sys
import time

args = sys.argv[1:]
mode = os.environ.get("FAKE_YTDLP_MODE", "ok")
if os.environ.get("FAKE_YTDLP_LOG"):
    with open(os.environ["FAKE_YTDLP_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps({"args": args, "electron_run_as_node": os.environ.get("ELECTRON_RUN_AS_NODE")}) + "\n")

if mode == "private":
    print("ERROR: [youtube] jNQXAC9IVRw: Private video. Sign in if you've been granted access to this video", file=sys.stderr)
    sys.exit(1)

if "--dump-single-json" in args:
    print(json.dumps({
        "id": "jNQXAC9IVRw", "title": "我的 第一支/影片", "channel": "Mocu", "duration": 3.0, "live_status": "not_live",
        "formats": [
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "filesize": 50000},
            {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 140, "filesize_approx": 48000},
            {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a.40.2"},
        ],
        "subtitles": {"zh-Hans": [{"ext": "vtt", "name": "中文（简体）"}], "live_chat": [{"ext": "json"}]},
        "automatic_captions": {"en": [{"ext": "vtt"}]},
    }, ensure_ascii=False))
    sys.exit(0)

out = args[args.index("--output") + 1]
total = os.path.getsize(os.environ["FAKE_YTDLP_WAV"])
for i in range(1, 5):
    print(f"MVR2T-PROGRESS {total * i // 4} {total} NA", flush=True)
    if mode == "slow":
        time.sleep(5)
shutil.copy(os.environ["FAKE_YTDLP_WAV"], out.replace("%(ext)s", "wav"))
if "--write-subs" in args and mode != "nosubs":
    lang = args[args.index("--sub-langs") + 1]
    with open(out.replace("%(ext)s", f"{lang}.vtt"), "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\n软件测试\n\n00:00:01.500 --> 00:00:03.000\n<c>与开会</c>\n")
