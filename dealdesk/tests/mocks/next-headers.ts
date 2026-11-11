// Stand-in for next/headers in route-handler tests: the test sets the signed session cookie, the route reads it
// through the real gate() and verifySession(). No header is ever set, so the audit session does not exist here.
export const JAR: { dd_session?: string } = {};
export async function cookies() { return { get: (name: string) => (name === "dd_session" && JAR.dd_session ? { name, value: JAR.dd_session } : undefined) }; }
export async function headers() { return { get: (_name: string) => null }; }
