import { randomBytes, scryptSync, timingSafeEqual } from "crypto";
import { appendRow, ENGINE_SHEET, readRanges, writeRange } from "./sheets";
import { asRole, type Role } from "./auth";

// Personal accounts live in the 'Users' tab of the engine sheet:
// A email, B name, C role, D status (pending | active | disabled), E pass_hash (scrypt, empty for Google-only),
// F via (password | google), G created, H approved_by, I approved_at, J last_login, K notes, L updated.
export type User = {
  row: number; email: string; name: string; role: Role; status: "pending" | "active" | "disabled";
  pass_hash: string; via: string; created: string; approved_by: string; approved_at: string; last_login: string; notes: string; updated: string;
};
export type PublicUser = Omit<User, "pass_hash" | "row">;

const TAB = "Users";
const COLS = ["email", "name", "role", "status", "pass_hash", "via", "created", "approved_by", "approved_at", "last_login", "notes", "updated"] as const;

export const now = () => new Date().toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(0, 16);
export const normEmail = (e: string) => String(e || "").trim().toLowerCase();
export const validEmail = (e: string) => /^[^\s@]{1,64}@[^\s@]{1,190}\.[a-z]{2,}$/i.test(e);

let cache: { at: number; users: User[] } | null = null;

export async function listUsers(fresh = false): Promise<User[]> {
  if (!fresh && cache && Date.now() - cache.at < 30_000) return cache.users;
  const rows = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:L500`]))?.[0] || [];
  const users: User[] = [];
  rows.forEach((r, i) => {
    const email = normEmail(r[0]);
    if (!email) return;
    const o: Record<string, string> = {};
    COLS.forEach((c, j) => { o[c] = String(r[j] ?? "").trim(); });
    const status = (["pending", "active", "disabled"].includes(o.status) ? o.status : "pending") as User["status"];
    users.push({ ...(o as Omit<User, "row" | "role" | "status" | "email">), row: i + 2, email, role: asRole(o.role), status });
  });
  cache = { at: Date.now(), users };
  return users;
}

export async function findUser(email: string, fresh = false): Promise<User | null> {
  const e = normEmail(email);
  return (await listUsers(fresh)).find((u) => u.email === e) || null;
}

export const publicUser = (u: User): PublicUser => {
  const { pass_hash: _h, row: _r, ...rest } = u; // eslint-disable-line @typescript-eslint/no-unused-vars
  return rest;
};

export function hashPassword(pw: string): string {
  const salt = randomBytes(16).toString("base64url");
  return `s1$${salt}$${scryptSync(pw, salt, 64).toString("base64url")}`;
}

export function verifyPassword(pw: string, stored: string): boolean {
  const [v, salt, hash] = String(stored || "").split("$");
  if (v !== "s1" || !salt || !hash) return false;
  try {
    return timingSafeEqual(scryptSync(pw, salt, 64), Buffer.from(hash, "base64url"));
  } catch {
    return false;
  }
}

// New account, always pending until an admin approves it in the panel.
export async function createUser(email: string, name: string, via: "password" | "google", passHash = "", notes = ""): Promise<User> {
  const t = now();
  await appendRow(TAB, [normEmail(email), name.slice(0, 80), "viewer", "pending", passHash, via, t, "", "", "", notes.slice(0, 200), t]);
  cache = null;
  return (await findUser(email, true))!;
}

export async function updateUser(email: string, patch: Partial<Pick<User, "name" | "role" | "status" | "pass_hash" | "approved_by" | "approved_at" | "last_login" | "notes">>): Promise<User | null> {
  const u = await findUser(email, true);
  if (!u) return null;
  const next = { ...u, ...patch, updated: now() };
  await writeRange(`'${TAB}'!A${u.row}:L${u.row}`, [COLS.map((c) => String(next[c] ?? ""))]);
  cache = null;
  return next;
}

// Touches last_login without blocking the login response.
export function touchLogin(email: string) {
  updateUser(email, { last_login: now() }).catch(() => {});
}
