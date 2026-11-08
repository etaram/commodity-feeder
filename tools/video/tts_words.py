"""Narration lines to mp3 plus word timings (seconds) per line, with edge-tts. Run in Actions; output goes to a scratch branch."""
import asyncio, json, pathlib, sys
import edge_tts
VOICE = sys.argv[3]; RATE = sys.argv[4] if len(sys.argv) > 4 else "+0%"
out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
async def one(key, text):
    try: c = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    except TypeError: c = edge_tts.Communicate(text, VOICE, rate=RATE)
    audio = bytearray(); words = []
    async for ch in c.stream():
        if ch["type"] == "audio": audio += ch["data"]
        elif ch["type"] == "WordBoundary": words.append([ch["text"], ch["offset"] / 1e7, ch["duration"] / 1e7])
    (out / f"{key}.mp3").write_bytes(bytes(audio)); return words
async def main():
    allw = {}
    for key, text in json.load(open(sys.argv[1])):
        for attempt in range(6):
            try: allw[key] = await one(key, text); print(key, "ok", len(allw[key])); break
            except Exception as e:  # noqa: BLE001
                print(key, "retry", attempt, e); await asyncio.sleep(3 + attempt * 3)
    (out / "words.json").write_text(json.dumps(allw))
asyncio.run(main())
