# Staging preview pinned to an exact commit

Why this procedure: the Vercel project `sinder-deal-desk` (prj_4kaUdFkTUOg4Pdbonp8Y2X6yxWy2, team
team_c69j2NjkbeSBqgAPLFYXasJM) has no Git link. Its deployments are uploaded files (`package.json` + `vercel.json`)
whose build script downloads the source from GitHub and builds `dealdesk/`. The stored build script downloads
**main**, so "redeploy the latest preview with withLatestCommit" rebuilds main, not the `staging` branch, and a
`gitSource` deployment is refused (no Git link; it also hits Vercel's GitHub rate limit, 429). To test a commit,
upload the same two files with the build script pointing at that exact commit.

## Steps

1. Move `staging` to the commit to test and note its full SHA:

   ```
   cd /home/claude/wt-server && git pull --ff-only
   git push origin HEAD:staging
   git ls-remote origin staging          # full SHA, e.g. 52b53b32d2366a20f91009d15673ae7dbd815669
   ```

2. Read the two source files of the latest preview (Vercel MCP):
   - `list_deployments {projectId: prj_4kaUdFkTUOg4Pdbonp8Y2X6yxWy2, teamId: team_c69j2NjkbeSBqgAPLFYXasJM, target: "preview", limit: 1}`
   - `list_deployment_files {id: <that id>, teamId}` -> `src/package.json` and `src/vercel.json` file uids
   - `get_deployment_file_contents {id, fileId: <uid>, teamId}` for each (base64), decode.

3. In `package.json` replace the archive in the `build` script (both places) with the SHA:

   ```
   "build": "curl -fsSL https://codeload.github.com/etaram/commodity-feeder/tar.gz/<SHA> | tar -xz --strip-components=2 commodity-feeder-<SHA>/dealdesk && ls app && next build"
   ```

   `vercel.json` is uploaded unchanged (the cron list).

4. Create the preview (no `target` = preview; Preview environment variables apply, so staging isolation holds):

   ```
   create_deployment {teamId: team_c69j2NjkbeSBqgAPLFYXasJM, requestBody: {
     name: "sinder-deal-desk", project: "prj_4kaUdFkTUOg4Pdbonp8Y2X6yxWy2",
     files: [{file: "package.json", encoding: "utf-8", data: <edited package.json>},
             {file: "vercel.json",  encoding: "utf-8", data: <vercel.json>}],
     meta: {source_commit: "<SHA>", branch: "staging"} }}
   ```

   Wait until `get_deployment {idOrUrl: <new id>, teamId}` says `READY` (about 2-3 minutes).

5. Check it (read-only route, answers 404 outside preview):

   ```
   web_fetch_vercel_url https://<deployment url>/api/staging-check
   ```

   Expect `"env":"preview"`, `"deployment":"<new id>"`, `"ok":true` (state sheet written and read back, live engine
   sheet write refused, mail cannot send, state sheet is not the engine sheet), and `ai_cap` with the expected
   `month_cap_usd`. `commit` is empty on these uploads; the pinned SHA is in the build script and in `meta.source_commit`.
   The admin routes (e.g. `/api/panel/spend`) need a login and cannot be fetched this way.

6. Production after the preview passes:

   ```
   gh workflow run server-ops.yml --ref release/server -f task=server-up
   gh run list --workflow server-ops.yml -L 1        # run id
   gh run watch <run id> --exit-status
   gh run view <run id> --log | grep -E "server-instance at|AI spend|OK: every|PROBLEMS"
   ```

   Expect `server-instance at <short SHA>`, `AI spend this month (estimate): $... of cap $<cap>` and
   `OK: every screen answered, none empty, none stale`.
