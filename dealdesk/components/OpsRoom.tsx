"use client";
import { useEffect, useRef, useState } from "react";
import type { FeedItem, MemberState, RoomView } from "@/lib/room";

// The operations room screen (app/room). Hebrew, right to left; names of team members and data stay in English.
// It shows what /api/room returns and nothing else, and asks again every 20 seconds while the tab is visible.
const REFRESH_MS = 20_000;
const STATE: Record<MemberState, string> = { working: "בעבודה עכשיו", waiting: "בהמתנה לבעלים", stalled: "ריצה תקועה", done_today: "הושלם היום", idle: "ללא פעילות" };
const KIND: Record<FeedItem["kind"], string> = { start: "התחלה", tool: "פעולה", proposed: "לאישור", approved: "אושר", rejected: "נדחה", sent: "נשלח", send_problem: "שליחה", question: "שאלה", finish: "סיום", stopped: "נעצר", error: "תקלה", scout: "סקאוט" };
const DECISION: Record<string, string> = { pursued: "נפתחה ריצה", "skipped: limit": "דילוג: מגבלה יומית", "skipped: outside focus": "דילוג: מחוץ למיקוד", "skipped: excluded country": "דילוג: מדינה מוחרגת", "skipped: low score": "דילוג: ציון נמוך",
  "skipped: not fresh": "דילוג: לא טרי", "skipped: no date": "דילוג: בלי תאריך", "skipped: deadline too close": "דילוג: דדליין קרוב מדי", "skipped: reserved for local bidders": "דילוג: שמור למקומיים", "skipped: start failed": "דילוג: הריצה לא נפתחה" };
const IL = "Asia/Jerusalem";
const time = (iso: string) => { const t = Date.parse(iso); return Number.isFinite(t) ? new Date(t).toLocaleTimeString("en-GB", { timeZone: IL, hour: "2-digit", minute: "2-digit" }) : ""; };
const dayOf = (iso: string) => { const t = Date.parse(iso); return Number.isFinite(t) ? new Date(t).toLocaleDateString("sv-SE", { timeZone: IL }) : ""; };
const stamp = (iso: string, today: string) => { const d = dayOf(iso); return !d ? "" : d === today ? time(iso) : `${d.slice(8, 10)}/${d.slice(5, 7)} ${time(iso)}`; };
const deal = (id: string) => `/?open=d:${encodeURIComponent(id)}`;

export default function OpsRoom({ first, firstError }: { first: RoomView | null; firstError: string }) {
  const [room, setRoom] = useState<RoomView | null>(first);
  const [err, setErr] = useState(firstError);
  const busy = useRef(false);
  useEffect(() => {
    let stop = false;
    const load = async () => {
      if (busy.current || document.hidden) return;
      busy.current = true;
      try {
        const r = await fetch("/api/room", { cache: "no-store" });
        const j = await r.json().catch(() => ({}));
        if (stop) return;
        if (r.ok && j.ok) { setRoom(j.room as RoomView); setErr(""); } else setErr(r.status === 401 ? "ההתחברות פגה. יש להתחבר מחדש." : `הנתונים לא התעדכנו (${j.error || r.status}).`);
      } catch { if (!stop) setErr("הנתונים לא התעדכנו: אין חיבור לשרת."); }
      finally { busy.current = false; }
    };
    const id = setInterval(load, REFRESH_MS);
    const vis = () => { if (!document.hidden) void load(); };
    document.addEventListener("visibilitychange", vis);
    return () => { stop = true; clearInterval(id); document.removeEventListener("visibilitychange", vis); };
  }, []);

  if (!room) return (<div className="room" dir="rtl" lang="he"><div className="room-head"><h1>חדר מבצעים</h1></div><div className="room-err">לא ניתן לקרוא את הנתונים{err ? `: ${err}` : "."}</div></div>);
  const c = room.counters, active = room.team.filter((m) => m.state !== "idle").length;
  return (
    <div className="room" dir="rtl" lang="he">
      <header className="room-head">
        <h1>חדר מבצעים</h1>
        <span className="sub">צוות הסוכנים של Sinder, מתוך הרשומות השמורות בלבד</span>
        <div className="state" aria-live="polite">
          <span><b className="mono">{room.running}</b> ריצות פעילות</span>
          <span><b className="mono">{room.waiting.length}</b> ממתינות לך</span>
          <span>סקאוטים: <b>{room.scout_on ? "פועלים" : "כבויים"}</b></span>
          <span className={err ? "stale" : ""}>עודכן <span className="mono ltr">{time(room.at)}</span>{err ? " (לא התעדכן)" : ""}</span>
        </div>
      </header>
      {err && <div className="room-err" role="status">{err}</div>}
      {room.notes.length > 0 && <div className="room-err" role="status">חלק מהמקורות לא נקראו, ולכן המסך חלקי: <span className="ltr">{room.notes.join("; ")}</span></div>}

      <section aria-label="שבעה ימים אחרונים">
        <div className="room-counters">
          <div><div className="n mono">{c.runs}</div><div className="l">ריצות סוכן{c.scout_runs ? `, מהן ${c.scout_runs} של סקאוטים` : ""}</div></div>
          <div><div className="n mono">{c.proposed}</div><div className="l">פניות שהוכנו</div></div>
          <div><div className="n mono">{c.approved}</div><div className="l">אושרו{c.rejected ? `, ${c.rejected} נדחו` : ""}</div></div>
          <div><div className="n mono">{c.sent}</div><div className="l">נשלחו בפועל</div></div>
          <div><div className="none">תשובות עדיין לא נקראות מתיבת הדואר</div><div className="l">תשובות שנרשמו</div></div>
          <div><div className="n mono ltr">${c.est_usd.toFixed(2)}</div><div className="l">עלות מודל מוערכת של הריצות</div></div>
        </div>
        <div className="room-caption">7 הימים האחרונים. כל מספר נספר מרשומות שמורות: ריצות ואישורים מיומן הסוכן, שליחות מיומן בקרת השליחה.</div>
      </section>

      <div className="room-grid">
        <div className="room-col">
          <section className="room-sec" aria-labelledby="r-wait">
            <h2 id="r-wait">ממתין לך <span>פניות שהוכנו ועוד לא אושרו</span></h2>
            {!room.waiting.length && <div className="empty">אין פניות שממתינות לאישור.</div>}
            {room.waiting.map((p) => (
              <div className="pend" key={p.id}>
                <div className="h"><span className="ltr">{p.to_name}</span> · <span className="ltr">{p.subject}</span></div>
                <div className="m">{p.by && <>הכין/ה: <span className="ltr">{p.by}</span> · </>}<span className="mono ltr">{stamp(p.at, room.day)}</span>{p.status !== "pending" && <> · <span className="flag">דורש בדיקה שלך לפני שליחה חוזרת</span></>}{p.unverified && <> · <span className="flag">הכתובת נמצאה ברשת ולא אומתה</span></>}</div>
                {p.why && <div className="m">למה: <span className="ltr">{p.why}</span></div>}
                <div className="m">האישור עצמו נעשה בטלגרם, בכפתורי אשר ודחה של ההודעה. {p.deal_id && <a href={deal(p.deal_id)}>פתח את העסקה</a>}</div>
              </div>
            ))}
          </section>

          <section className="room-sec" aria-labelledby="r-team">
            <h2 id="r-team">הצוות <span>{active} מתוך {room.team.length} עם פעילות רשומה</span></h2>
            <div className="team">
              {room.team.map((m) => (
                <article className={`mem ${m.state}`} key={m.id}>
                  <div className="top"><span className="dot" aria-hidden="true" /><span className="name ltr">{m.name}</span><span className="tag">{STATE[m.state]}</span></div>
                  <div className="role">{m.he} · {m.region}</div>
                  {m.now ? <div className="now">{m.now}{m.deal_id && <> · <a href={deal(m.deal_id)}>העסקה</a></>}</div> : <div className="now" style={{ color: "var(--soft)" }}>אין משימה פתוחה.</div>}
                  <div className="foot">{m.last_active ? <>פעילות אחרונה: <span className="mono ltr">{stamp(m.last_active, room.day)}</span>{m.today ? ` · ${m.today} פעולות היום` : ""}</> : "אין פעילות רשומה."}</div>
                </article>
              ))}
            </div>
            <div className="note">ריצה אחת של הסוכן מבצעת את כל התפקידים. השיוך לחבר צוות נקבע לפי כלל: הכלי האחרון שהריצה הפעילה, מי שחתום על פנייה שהוכנה, ומי שהסקאוט שיבץ. חבר צוות בלי רשומה מוצג ללא פעילות.</div>
          </section>
        </div>

        <div className="room-col">
          <section className="room-sec" aria-labelledby="r-feed">
            <h2 id="r-feed">יומן חי <span>החדש למעלה, מתעדכן כל 20 שניות</span></h2>
            {!room.feed.length && <div className="empty">עוד אין אירועים רשומים.</div>}
            <ol className="feed">
              {room.feed.map((f, i) => (
                <li key={`${f.at}-${i}`} className={f.kind}>
                  <span className="t mono ltr">{stamp(f.at, room.day)}</span>
                  <span className="x"><span className="k">{KIND[f.kind]}</span>{f.text}{f.who && <span className="w"> · <span className="ltr">{f.who}</span></span>}{f.deal_id && <span className="w"> · <a href={deal(f.deal_id)}>עסקה</a></span>}</span>
                </li>
              ))}
            </ol>
            <div className="note">שעת פעולה היא שעת שמירת הצעד שבו הופיעה (צעד נשמר כל כמה פניות למודל). חיפושי רשת של הסוכן אינם נשמרים ולכן אינם מופיעים.</div>
          </section>

          <section className="room-sec hunt" aria-labelledby="r-hunt">
            <h2 id="r-hunt">הציד של היום <span>אותות שהסקאוטים בדקו</span></h2>
            {!room.scout_on && !room.hunt.looked && <div className="empty">הסקאוטים כבויים (SCOUT). שום אות לא נבדק היום.</div>}
            {room.scout_on && !room.hunt.looked && <div className="empty">הסקאוטים פועלים, והיום עוד לא נרשמה בדיקה.</div>}
            {room.hunt.looked > 0 && (
              <div className="hunt-sum">
                <span><b className="mono">{room.hunt.looked}</b> נבדקו</span><span><b className="mono">{room.hunt.pursued}</b> נפתחו לריצה</span>
                {room.hunt.skipped.map((s) => (<span key={s.reason}><b className="mono">{s.n}</b> {DECISION[s.reason] || s.reason}</span>))}
              </div>
            )}
            {room.hunt.items.map((h, i) => (
              <details key={`${h.at}-${i}`} className={h.decision === "pursued" ? "pursued" : ""}>
                <summary><span className="sc mono">{h.score}</span><span className="lb"><span className="ltr">{h.label}</span></span><span className="dc">{DECISION[h.decision] || h.decision}</span></summary>
                <ul>
                  <li>{h.kind === "winner" ? "זוכה טרי בחוזה" : "מכרז חדש"} · <span className="mono ltr">{stamp(h.at, room.day)}</span>{h.assignees.length > 0 && <> · שובץ: <span className="ltr">{h.assignees.join(", ")}</span></>}{h.deal_id && <> · <a href={deal(h.deal_id)}>העסקה</a></>}</li>
                  {h.reasons.map((r, k) => (<li key={k} className="ltr" style={{ textAlign: "left" }}>{r}</li>))}
                </ul>
              </details>
            ))}
          </section>
        </div>
      </div>
    </div>
  );
}
