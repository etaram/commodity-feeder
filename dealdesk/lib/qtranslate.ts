import { claude } from "@/lib/anthropic";
import { logEvent } from "@/lib/log";

// Search words typed in Hebrew (or another non-Latin script) are translated to English before matching, because
// tender titles and supplier records are in English (or the source language, translated to English).
// Order: a small built-in dictionary of common trade terms (free, instant), then the AI (cheapest model, cached).
// Flag: QUERY_TRANSLATE=off turns it off without a redeploy of the client.
export const NON_LATIN = /[֐-׿؀-ۿЀ-ӿ฀-๿぀-ヿ一-鿿가-힯]/;

const DICT: Record<string, string> = {
  "גנרטור": "generator", "גנרטורים": "generators", "גנרטור דיזל": "diesel generator", "דיזל": "diesel", "סולר": "diesel",
  "התפלה": "desalination", "מתקן התפלה": "desalination plant", "מים": "water", "ביוב": "sewage", "שפכים": "wastewater",
  "צינורות": "pipes", "צינור": "pipe", "משאבה": "pump", "משאבות": "pumps", "שנאי": "transformer", "שנאים": "transformers",
  "כבלים": "cables", "כבל": "cable", "סולארי": "solar", "פאנלים סולאריים": "solar panels", "אנרגיה סולארית": "solar energy",
  "סוללות": "batteries", "אגירה": "energy storage", "חשמל": "electricity", "מוצרי חשמל": "electrical appliances",
  "שואבי אבק": "vacuum cleaners", "שואבי אבק רובוטיים": "robot vacuum cleaners", "רובוט": "robot",
  "חיטה": "wheat", "תירס": "maize", "אורז": "rice", "סוכר": "sugar", "שמן": "oil", "שמן צמחי": "vegetable oil",
  "שמן חמניות": "sunflower oil", "שמן דקלים": "palm oil", "קמח": "flour", "סויה": "soybean", "קפה": "coffee", "שומשום": "sesame",
  "דשן": "fertilizer", "דשנים": "fertilizers", "אוריאה": "urea", "פלדה": "steel", "ברזל": "iron", "אלומיניום": "aluminium",
  "נחושת": "copper", "מלט": "cement", "בטון": "concrete", "אספלט": "asphalt", "דלק": "fuel", "גז": "gas",
  "פולימרים": "polymers", "פלסטיק": "plastic", "נייר": "paper", "תאית": "pulp", "ציוד רפואי": "medical equipment",
  "תרופות": "pharmaceuticals", "בית חולים": "hospital", "מרכז נתונים": "data center", "מרכזי נתונים": "data centers",
  "נמל": "port", "נמלים": "ports", "לוגיסטיקה": "logistics", "כבישים": "roads", "גשר": "bridge", "רכבת": "railway",
  "רכבים": "vehicles", "משאיות": "trucks", "אוטובוסים": "buses", "מזגנים": "air conditioners", "מיזוג אוויר": "air conditioning",
  "תאורה": "lighting", "פנסי רחוב": "street lights", "מחשבים": "computers", "מצלמות": "cameras", "אבטחה": "security",
  "ביטחון": "defence", "מדים": "uniforms", "טקסטיל": "textiles", "מזון": "food", "בשר": "meat", "עוף": "chicken",
  "דגים": "fish", "חלב": "milk", "פירות": "fruit", "ירקות": "vegetables", "בנייה": "construction", "מבנים": "buildings",
};

const cache = new Map<string, string>();

export async function toEnglish(q: string): Promise<{ text: string; how: "none" | "dict" | "ai" | "failed" }> {
  const raw = String(q || "").trim().slice(0, 200);
  if (!raw || !NON_LATIN.test(raw) || process.env.QUERY_TRANSLATE === "off") return { text: raw, how: "none" };
  const key = raw.toLowerCase();
  if (DICT[key]) return { text: DICT[key], how: "dict" };
  // every word known: translate word by word (the longest known phrase first)
  const words = key.split(/[\s,]+/).filter(Boolean);
  if (words.every((w) => DICT[w] || !NON_LATIN.test(w))) return { text: words.map((w) => DICT[w] || w).join(" "), how: "dict" };
  const hit = cache.get(key);
  if (hit) return { text: hit, how: "ai" };
  if (!process.env.ANTHROPIC_API_KEY) return { text: raw, how: "failed" };
  try {
    const { text } = await claude({
      max_tokens: 60,
      messages: [{ role: "user", content: `Translate this search for public tenders or suppliers into English search keywords: the product, service or place names a tender title or a supplier catalogue would use. 1 to 6 words, lower case, no quotes, no explanation. Keep country names. Search: ${raw}` }],
    }, { job: "translate query" });
    const en = text.replace(/["'\n]/g, " ").replace(/\s+/g, " ").trim().toLowerCase().slice(0, 80);
    if (!en || NON_LATIN.test(en)) return { text: raw, how: "failed" };
    if (cache.size > 2000) cache.delete(cache.keys().next().value as string);
    cache.set(key, en);
    return { text: en, how: "ai" };
  } catch (e) {
    void logEvent("warn", "translate", "query translation failed", String(e).slice(0, 200));
    return { text: raw, how: "failed" };
  }
}

// A regex that needs every word (word start, any order), for short searches.
export function allWordsRe(text: string): RegExp | null {
  const w = [...new Set(text.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((x) => x.length >= 2))].slice(0, 6);
  if (!w.length) return null;
  const stem = (x: string) => (x.length > 4 && x.endsWith("s") && !x.endsWith("ss") ? x.slice(0, -1) : x); // plural = singular
  return new RegExp(w.map((x) => `(?=.*(?:^|[^\\p{L}])${stem(x)})`).join(""), "iu");
}
