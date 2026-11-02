# Deal Desk users and roles

Personal accounts live in the `Users` tab of the Leads Engine sheet. Never put passwords or secrets in this file.

## Roles

| Role | Can |
|---|---|
| viewer | Read every screen and tab |
| analyst | Also run research jobs, record Go/Watch/No decisions, start bid projects, use the AI features |
| admin | Also approve project actions (RFQs, commitments, prices), close projects, approve access requests and change roles |

The shared team login (`TEAM_USER` + `TEAM_PASSCODE` in Vercel) always signs in as admin. It is the bootstrap account: keep it, change its passcode in Vercel when needed.

## How people get in

1. **Request access** on the sign-in page (name, email, password) or **Sign in with Google**. Either way a `pending` row appears in `Users`.
2. An admin opens the panel, tab **Users**, and presses **Approve** (optionally changes the role first). Default role: viewer.
3. The person signs in. A role change takes effect at their next sign-in (sessions last 30 days; signing out and in applies it at once).

Disable: tab Users, **Disable**. The person cannot sign in again until re-enabled.

## Google sign-in (one-time setup, owner's Google account)

1. Google Cloud Console, APIs & Services, **OAuth consent screen**: External, app name "Sinder Deal Desk", your support email. While the app is in "Testing", only emails listed under Test users can sign in (up to 100). Publish the app to lift that.
2. **Credentials**, Create credentials, **OAuth client ID**, type Web application.
   Authorized JavaScript origin: `https://sinder-deal-desk.vercel.app`
   Authorized redirect URI: `https://sinder-deal-desk.vercel.app/api/auth/google/callback`
3. In Vercel, project sinder-deal-desk, Settings, Environment Variables (Production and Preview):
   `GOOGLE_CLIENT_ID` = the client ID, `GOOGLE_CLIENT_SECRET` = the client secret (type: sensitive).
4. Redeploy. The "Sign in with Google" button appears on the sign-in page.

Google accounts never get a password here; they are matched by verified email to the `Users` row.

## Server rules

- `middleware.ts` checks the signed session cookie on every request.
- `lib/gate.ts` checks the role in every API route that writes or spends tokens.
- `/api/panel/append`: job types `approval` and `project_close` are admin only; every queued job records `by=<email>` in its notes.
- `/api/users` (admin): list, approve, role, disable. Password hashes (scrypt) never leave the server.

## Email on new access requests

Every new request (password or Google) emails the admin through Resend.
Vercel env: `RESEND_API_KEY` (required), `NOTIFY_EMAIL` (default: the owner), `NOTIFY_FROM` (optional).
Without a verified domain in Resend, mail can only go to the email the Resend account was opened with.
