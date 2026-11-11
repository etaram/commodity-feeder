// Failed-attempt limiter (sign-in hardening, acceptance F18). Pure logic with an injected clock so it is unit-testable.
// Counters live in memory, so they are per server instance: on serverless each warm instance counts on its own and a
// cold start forgets. That slows guessing but is not a hard global cap; a shared store comes with PostgreSQL.
export type Limiter = {
  /** Seconds until the key may try again; 0 when it is not blocked. */
  retryAfter(key: string, now?: number): number;
  /** Records one failed attempt. Returns true when this failure is the one that reaches the limit. */
  fail(key: string, now?: number): boolean;
  /** Forgets the key (after a successful sign-in). */
  clear(key: string): void;
  /** True once per blocked window per key, so a hammering client writes one log row and not thousands. */
  noteBlocked(key: string, now?: number): boolean;
  size(): number;
};

export function createLimiter(max = 8, windowMs = 15 * 60e3, maxKeys = 20_000): Limiter {
  const hits = new Map<string, { at: number[]; noted: number }>();
  const live = (key: string, now: number) => {
    const e = hits.get(key);
    if (!e) return null;
    e.at = e.at.filter((t) => now - t < windowMs);
    if (!e.at.length) { hits.delete(key); return null; }
    return e;
  };
  // Sliding window: blocked while `max` failures are inside the window; frees up when the oldest of them ages out.
  const retryAfter = (key: string, now = Date.now()) => {
    const e = live(key, now);
    if (!e || e.at.length < max) return 0;
    return Math.max(1, Math.ceil((e.at[e.at.length - max] + windowMs - now) / 1000));
  };
  return {
    retryAfter,
    fail(key, now = Date.now()) {
      const e = live(key, now) || { at: [], noted: 0 };
      e.at = [...e.at, now].slice(-max); // only the last `max` matter, which also bounds memory per key
      hits.delete(key); hits.set(key, e); // re-insert: Map order = least recently failed first
      if (hits.size > maxKeys) { // bounded: drop expired keys, then the least recently failed (an attacker cannot grow it without limit)
        for (const k of [...hits.keys()]) live(k, now);
        for (const k of hits.keys()) { if (hits.size <= maxKeys) break; hits.delete(k); }
      }
      return e.at.length === max;
    },
    clear(key) { hits.delete(key); },
    noteBlocked(key, now = Date.now()) {
      const e = live(key, now);
      if (!e || e.at.length < max) return false;
      const start = e.at[e.at.length - max];
      if (e.noted === start) return false;
      e.noted = start;
      return true;
    },
    size: () => hits.size,
  };
}

// Sign-in: 8 failed attempts per 15 minutes, counted per IP and per e-mail (keys "ip:..." and "email:...").
export const LOGIN_MAX_FAILS = 8, LOGIN_WINDOW_MS = 15 * 60e3;
export const loginLimiter = createLimiter(LOGIN_MAX_FAILS, LOGIN_WINDOW_MS);
export const loginKeys = (ip: string, email: string) => ({ ip: `ip:${String(ip || "?").slice(0, 80)}`, email: `email:${String(email || "").trim().toLowerCase().slice(0, 200)}` });
