// "Check the website" from the panel (app/api/panel/company-check): pure helpers shared by the route and its tests.
// The check-now worker on the server (leads/check_now.py) answers a request within about a minute; the hourly job
// still reads the same queue.

// A website given with a request: an http(s) URL with a dotted host, else "" (a bare domain gets http://). The same
// rule as clean_site in leads/check_now.py, so a value the route accepts is one the worker accepts.
export function cleanWebsite(v: unknown): string {
  const first = String(v ?? "").trim().split(/\s+/)[0] || "";
  let u = first;
  if (u && !/^https?:\/\//i.test(u) && /^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(\/|$)/.test(u)) u = "http://" + u;
  return /^https?:\/\/[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?::\d{2,5})?(?:\/\S*)?$/.test(u) ? u.slice(0, 300) : "";
}

// Column D of 'Company checks': a date ("2026-11-12", hourly job) or the full time of a check-now result
// ("2026-11-12T12:30:41Z"). The panel shows the date and waits for a check_at newer than its request.
export function checkedParts(d: string): { checked: string; checked_at: string } {
  const s = String(d || "");
  return { checked: s.slice(0, 10), checked_at: /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) ? s : "" };
}

// Has the check answered this request? (time of the check not older than the request, 5 s of clock slack)
export function answers(checkedAt: string, requestedAt: string): boolean {
  const a = Date.parse(checkedAt), b = Date.parse(requestedAt);
  return Number.isFinite(a) && Number.isFinite(b) && a >= b - 5000;
}
