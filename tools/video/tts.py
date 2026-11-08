"""Render the narration lines to mp3 (one file per scene) with edge-tts. Run in Actions; output goes to a scratch branch."""
import asyncio, json, pathlib, sys
import edge_tts
VOICE = sys.argv[3] if len(sys.argv) > 3 else "en-US-AndrewNeural"
out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
async def main():
    for key, text in json.load(open(sys.argv[1])):
        for attempt in range(5):
            try:
                await edge_tts.Communicate(text, VOICE, rate="-2%").save(str(out / f"{key}.mp3")); print(key, "ok"); break
            except Exception as e:  # noqa: BLE001
                print(key, "retry", attempt, e); await asyncio.sleep(3 + attempt * 3)
asyncio.run(main())
