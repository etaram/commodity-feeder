# Sinder brand film, vertical

GOAL:    an investor or partner who watches once on a phone understands that Sinder turns 34,644 live tenders into ranked, priced, evidenced deals, and writes to Etamar@sinder.pro.
OUTPUT:  HyperFrames, 1080 x 1920, 30 fps, rendered at portrait-4k and downscaled for sharpness.
TIME:    63.5 s x 30 = 1905 frames. The narration is the clock: every element lands on its word (word times from the TTS engine).
DEVICE:  a trader's day (09:12, 11:40, 12:15, 14:21) as time chips; form: object-to-object chain.
SPINE:   one real tender (France, laboratory and optical equipment, Resah, $182.9M, 26 days, fit 73.6, EV $1.74M, win 15%) travels list -> card -> suppliers -> bid. Origin price beat uses real UCDA data (Bugisu AA $2.72/lb, 6 Nov).

LOOK:
  worlds  map (navy #0B1324, dot map filling the width, inactive dots #24345A r 2.4, live dots #F0CF7A r 2.4-6.4)
          phone (gold #E9B949 ground, navy ink), product close-up (light #EDF0F5 ground, product dark cards #101A30),
          board (navy, split-flap rows #1B2847 on #0B1324), Telegram (#2AABEE ground, white ink), end card (navy).
  type    display Barlow Condensed 700, 9% of height for hero numbers (170-300 px), titles 110-130 px, tracking -1%;
          UI and labels IBM Plex Sans 500/600, 32-44 px; nothing under 28 px.
  accent  gold #F0CF7A on navy, deep gold #9A6B12 on light grounds, green #22A565 only for live/approved states.
  depth   phone contact shadow 0 40 px 90 px rgba(0,0,0,.35); no glow, no grain, no glass.
  icons   real brand marks (WhatsApp, Gmail, Telegram from Simple Icons), flags from flag-icons; PDF/DOCX as generic file glyphs.
MOTION:  arrive expo.out 0.5 s; camera/flood power2.inOut 0.5 s; exits power3.in, 40% shorter; titles per word blur 6->0 in 0.13 s, 0.067 s apart, no translate;
         stagger list items 0.06 s. Landed titles hold still.
TRANSITIONS: zoom through the Israel dot (map -> gold), swipe-clear then zoom through the app icon (phone -> navy), carry (mark -> app header),
         lift (list row -> card), whip (card -> price world), colour flood (navy -> Telegram blue), blur swap on the board.
SOUND:   old way near silence (riser + notification pings rotating 2 takes), music opens on the brand reveal at a strong bar
         ("The Corporate Upbeat", Soundrider/Dope, CC BY 3.0), ducked under voice to ~0.16; whoosh on scene cuts (3 takes rotated),
         pop on chips/numbers, click on real taps, one impact on the brand, one on "Let's talk".
BANNED:  dark void with small floating things, glow/bloom/particles, glass cards, purple gradients, UI tilted in 3D,
         three cards in a row, docked corner logo or LIVE pill, titles drifting after landing, click rings, serif italics,
         screen titles repeating the narration word for word (subtitles carry the words).
QA:      t=0.0 (thumbnail not empty), 4.0, 10.0, 16.0, 21.5, 24.5, 28.0, 33.0, 38.0, 42.0, 50.0, 58.5, 62.0.
