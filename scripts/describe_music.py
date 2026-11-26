"""A machine 'pre-listen' of the score candidates: Gemini describes each (instruments, vocals,
artifacts). Only our own generated music is sent. The result goes to outputs/music/describe.json."""
import json
import subprocess
from pathlib import Path

from pipeline.common import ffmpeg
from pipeline.common.cache import atomic_write_json, sha256_bytes
from pipeline.common.invoke import invoke
from pipeline.common.log import start_run
from pipeline.providers import registry

start_run("free")
providers = registry.get_provider("transcribe").providers
SCHEMA = {"type": "object", "properties": {
    "instruments": {"type": "string"}, "tempo_feel": {"type": "string"}, "mood": {"type": "string"},
    "vocals": {"type": "string"}, "structure": {"type": "string"}, "artifacts": {"type": "string"},
    "ending": {"type": "string"}, "fits_brief": {"type": "string"}},
    "required": ["instruments", "tempo_feel", "mood", "vocals", "structure", "artifacts", "ending", "fits_brief"]}
PROMPT = ("You are reviewing an instrumental track generated as a film score for a 75-second family film, "
          "to sit quietly under English narration. The brief was: gentle nostalgic instrumental, Ethiopian "
          "tizita-style melody, soft fingerpicked krar and warm acoustic guitar, light washint flute, slow tempo, "
          "sparse and intimate, warm hopeful ending. Listen to the whole track and answer briefly and honestly: "
          "instruments you hear; tempo feel; mood; any vocals, singing or humming (say 'none' if none); "
          "structure over time (with rough timestamps); audible artifacts, glitches, distortion or abrupt changes "
          "(say 'none' if none); how it ends; and whether it fits the brief (one sentence).")
out = {}
for n in (1, 2, 3):
    man = json.loads(Path("outputs/music/manifest.json").read_text(encoding="utf-8"))[f"main_c{n}"]
    mp3 = Path(f"outputs/cuts/tmp/main_c{n}.mp3")
    ffmpeg.run(["-i", man["path"], "-ac", "1", "-b:a", "96k", str(mp3)])
    data = mp3.read_bytes()
    r = invoke(providers, lambda p: p.generate_json(PROMPT, SCHEMA, attachments=[(data, "audio/mp3")]),
               stage="music_check", shot_id=f"main_c{n}", input_hash=sha256_bytes(data), max_attempts=2)
    out[f"main_c{n}"] = {**r.value.data, "model": r.provider.model}
    print(f"main_c{n}:", json.dumps(r.value.data, indent=1, ensure_ascii=False))
atomic_write_json(Path("outputs/music/describe.json"), out)
