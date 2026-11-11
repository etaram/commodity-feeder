import assert from "node:assert/strict";
import { renderMail, splitSignature } from "../lib/mailhtml";

const t = "Dear Mr Chen,\n\nWe are looking for 200 t of <HDPE> pipe grade. See https://example.com/spec.\n\nBest regards,\nMei Lin Zhang, Supplier Relations, East and South-East Asia, Sinder";
const s = splitSignature(t);
assert.equal(s.signer?.name, "Mei Lin Zhang");
assert.ok(!s.body.includes("Mei Lin Zhang"), "signature line leaves the body");
assert.ok(s.body.endsWith("Best regards,"), "the closing stays");
const h = renderMail({ text: t, from: "desk@sinder.pro" });
assert.ok(h.includes("SINDER") && h.includes('href="https://sinder.pro"') && h.includes("Supplier Relations, East and South-East Asia") && h.includes("mailto:desk@sinder.pro"));
assert.ok(h.includes("&lt;HDPE&gt;") && !h.includes("<HDPE>"), "text is escaped");
assert.ok(h.includes('href="https://example.com/spec"'), "links are clickable, without the closing full stop");
assert.equal((h.match(/Mei Lin Zhang/g) || []).length, 1, "the name appears once");
assert.equal((h.match(/<img/g) || []).length, 1, "one image: the logo"); assert.ok(!/<script/i.test(h));
const he = renderMail({ text: "שלום,\n\nזו הודעת בדיקה.", from: "desk@sinder.pro", fromName: "Etamar", fromTitle: "Managing Director" });
assert.ok(he.includes('dir="rtl"') && he.includes("Managing Director"));
assert.equal(splitSignature("Hello\n\nno signature here").signer, null);
assert.ok(h.includes("Everything you need"), "slogan in the header");
console.log("mailhtml: ok");
