// Runs once when the Next server starts. On our own long-running server (not Vercel) it starts the keep-warm of the
// panel's live Sheets tabs at boot, so the first visit after a restart or a quiet spell does not meet Google's slow
// first read of a spreadsheet (13-25 s) and fall back to the older snapshot. See keepWarm in lib/panel.ts.
// The NEXT_RUNTIME test must stay in this exact form: the edge bundle drops the Node-only import only then.
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    if (process.env.VERCEL) return;
    const { keepWarm } = await import("./lib/panel");
    keepWarm();
  }
}
