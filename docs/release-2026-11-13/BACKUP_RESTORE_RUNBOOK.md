# Backup and restore runbook

Status on 11 Nov 2026: the database backup runs nightly. The Google Sheets backup is written and unit-tested but has
not yet run on the server (it needs the secrets below). Recovery time has not been measured. Acceptance test: F21.

## What is backed up

| What | How | When |
|---|---|---|
| PostgreSQL database (nearly empty today) | `deploy/ops/_backup_root.sh`: dump, encrypt, restore into a throw-away database to prove it opens | nightly, 01:40 UTC, workflow `backup` |
| Google Sheets state: users, deals, approvals, logs, agent runs, outreach, hand-kept input tabs | `tools/backup_sheets.py`: one JSON-lines file per tab plus `manifest.json`, checked, then packed and encrypted | same workflow, after the database |
| Repository | full mirror clone at `/opt/sinder/backup/commodity-feeder.git`, made once by `deploy/bootstrap.sh` | once, at server setup (no refresh found in the repository) |

The Sheets tab list is in `tools/backup_sheets.py` with the reason for each group: the state tabs of
`dealdesk/lib/sheets.ts` (a test fails when the two lists differ), the other tabs the app appends to in the engine
sheet, eight hand-kept input tabs, and two app-written tabs of the supplier universe sheet.

## Where the copies live

| Place | Database | Sheets | Kept |
|---|---|---|---|
| Server | `/opt/sinder/backup/db/*.sql.gz.enc` | `/opt/sinder/backup/sheets/*.tar.gz.enc` | 14 days |
| Google Drive (rclone remote `gdrive`, only when the owner has connected it) | `Sinder-Backups/db` | `Sinder-Backups/sheets` | 60 days |
| Workflow artifacts (GitHub, run page of `backup`) | `sinder-db-backup` | `sinder-sheets-backup` | 30 days |
| The owner's Mac | nothing automatic. A copy is there only when the owner downloads an artifact or syncs the Drive folder | same | by hand |

Every copy is the same AES-256 encrypted file. The key is `/opt/sinder/backup.key` on the server, readable by root
only. **The key exists only on the server.** If the server is lost, every copy on Drive, GitHub and the Mac is
unreadable. The owner should keep one copy of the key in a password manager; this is not done by any script.

## How to decrypt

On the server, as root (the key is never copied or printed):

    cd /root && mkdir -p restore && cd restore
    # Sheets export
    openssl enc -d -aes-256-cbc -pbkdf2 -pass file:/opt/sinder/backup.key \
      < /opt/sinder/backup/sheets/sinder-sheets-<time>.tar.gz.enc | tar -xzf -
    # database dump
    openssl enc -d -aes-256-cbc -pbkdf2 -pass file:/opt/sinder/backup.key \
      < /opt/sinder/backup/db/sinder-<time>.sql.gz.enc | gunzip > sinder.sql

For a file downloaded from Drive or from a workflow artifact the command is the same, with the path of that file.
Delete the plain files when done: they hold users, contacts and deal data.

## How to check a Sheets export

    python3 tools/restore_sheets_check.py restore/sheets-export

One line per tab: `OK` with the row and column count, or `FAIL` with the reason (hash differs, rows missing, file
missing, a file that is not in the manifest). `absent` means the tab did not exist in the spreadsheet on that night.
The check reads local files only. The nightly workflow runs it before encrypting, and the server reads the encrypted
file back and compares the manifest inside it.

## The guard against backing up a wiped sheet

The server keeps the row counts of the last good export (`/opt/sinder/backup/sheets/last-manifest.json`, no cell
content). When a guarded tab now has fewer than half the rows it had, or has disappeared, the workflow fails and no new
backup is written. The older encrypted files stay untouched. If the loss was intended (a log was trimmed on purpose),
run the workflow by hand with `allow_shrink` set to the tab names, or `all`.

## Restoring the database

    # decrypt as above, then on the server:
    cd /opt/sinder/repo/deploy
    docker compose exec -T db psql -U sinder -d postgres -c "create database sinder_restored"
    docker compose exec -T db psql -U sinder -d sinder_restored < /root/restore/sinder.sql

Restore into a new database first, look at it, then switch. Replacing the live database needs the owner's approval.

## Writing a Sheets export back (not automated, needs owner approval)

No tool in the repository writes a backup into the live spreadsheets. This is on purpose: a write-back replaces live
data. (`tools/restore_sheets.py` writes into a new, empty spreadsheet only and refuses the live ones; see "Restore
drill" below. It can do step 4 of this list.) Writing back is a separate step, done only after the owner approves it in writing, in this order:

1. Decrypt and check the export (above). Stop on any `FAIL`.
2. Stop the writers: pause the Vercel deployment and the scheduled workflows that write to the sheets.
3. Make a copy of the damaged spreadsheet in Google Drive (File > Make a copy). Never restore over the only copy.
4. Restore into a **new** spreadsheet first: one tab per `.jsonl` file, each line is one row. Tabs marked
   `"render": "UNFORMATTED_VALUE"` in the manifest are written as plain values (RAW), tabs marked `FORMULA` as typed
   input (USER_ENTERED) so their formulas work again.
5. Compare row counts with the manifest, let the owner look at Users, Deal Records and Agent Approvals.
6. Either point the app at the new spreadsheet (`STATE_SHEET_ID` in Vercel and in the GitHub secret) or copy the
   tabs into the old one. Start the writers again.

Google's own version history (File > Version history) is often the faster way back for a single damaged tab.

## Restore drill

Proves that the newest Sheets backup can be written into a spreadsheet and read back unchanged. Workflow
`restore-drill` (run by hand), tool `tools/restore_sheets.py`, server part `deploy/ops/_restore_root.sh`.
Written and unit-tested on 12 Nov 2026 with a fake Sheets API; **not yet run against Google**.

How to run it:

1. In Google Drive create a new, empty spreadsheet. Share it with the service account (the `client_email` of
   `GOOGLE_SERVICE_ACCOUNT_JSON`) as **Editor**. Keep it private: no "anyone with the link".
2. Copy its id: the long part of the address between `/d/` and `/edit`.
3. GitHub > Actions > `restore-drill` > Run workflow, paste the id into `target`. `only` restores a few tabs
   (names separated by commas) for a quick trial.
4. When the run is over, **delete the target spreadsheet**: it now holds a full copy of users, contacts and deals.

What the run does: decrypts the newest `/opt/sinder/backup/sheets/*.enc` on the server into a work directory only
the runner user can read, checks it like `restore_sheets_check.py`, creates one tab per exported tab in the target,
writes the rows as plain values (RAW: a formula of a hand-kept tab arrives as its text and is not evaluated), reads
every tab back and compares. The work directory is removed at the end, also when a step fails.

The tool refuses to write (exit code 2, nothing sent) when the target is the engine, state or universe spreadsheet,
when a tab of the target with the same name as a tab to restore already holds data, or when the export is damaged.
A second run therefore needs a fresh spreadsheet (or the restored tabs deleted from the first one).

What counts as a pass: every tab line starts with `OK` and the last line says `restore drill PASSED: N of N tabs
match`. For each tab the rows and columns read back equal the manifest and the content hash is equal. The hash is
made as in the backup (sha256 over one compact JSON array per row) after both sides are normalised the same way:
an empty cell is `""`, empty cells at the end of a row and empty rows at the end of a tab are dropped, a number
without a fraction is an integer. Text is compared exactly. `(byte-identical)` on a line means the tab matched even
without that normalising. The log holds tab names and counts only, never a cell.

On a mismatch (`FAIL`, the run ends red):

- `REFUSED` as the last line: nothing was written. Read the reason (live spreadsheet, target not empty, export
  failed the check, target not shared with the service account) and fix that.
- `HTTP 403` on a tab: the service account is not an editor of the target. `HTTP 429` after six tries: Google's
  quota; wait a few minutes and run again into a fresh spreadsheet, or use `only`.
- `first difference at row R, column C`: the cell came back different from the export. Decrypt the same backup on
  the server (above), look at line R of that tab's `.jsonl` file and at the cell in the target spreadsheet. Known
  candidates that this drill has not yet met in real data: a number with more than 15 significant digits, a cell
  longer than 50,000 characters, text that Sheets stores differently from what was sent. If the export is right
  and only the comparison is too strict, the rule to change is `normalise()` in `tools/restore_sheets.py`, with a
  test; if the cell was written wrongly, the backup of that tab cannot be trusted for a real restore until fixed.
- rows `X of Y` with X smaller: a write was cut short. Run again into a fresh spreadsheet; if it repeats on the same
  tab, restore that tab alone with `only` and report the line.
- A failed drill does not touch the backups or the live sheets. Do not treat the backup as proven until a run passes.

The database has its own drill every night: `deploy/ops/_backup_root.sh` restores the dump it just wrote into the
throw-away database `restore_test`, reads the probe row back and drops it. It reads one row, not every table.

## What the workflow needs

- Secret `GOOGLE_SERVICE_ACCOUNT_JSON` (exists; the service account must be able to read all three spreadsheets).
- Secret `STATE_SHEET_ID`: the id of the state spreadsheet, the same value the app has in Vercel. **New.** Without it
  the Sheets steps stop with an error instead of silently backing up old copies of the state tabs.
- On the server: `/opt/sinder/backup.key` (created by the first database backup), and rclone remote `gdrive` for Drive.

## What is NOT covered

- The backup key itself (see above).
- The bulk data tabs written by the collectors (Tenders, Awards, Suppliers and the like) and the rest of the supplier
  universe sheet: they are rebuilt from the repository and its data jobs, which has not been timed either.
- Formatting, charts, sharing settings, protected ranges, Apps Script and hidden-tab flags of the spreadsheets.
- Tabs added to the app after 11 Nov 2026 that are not in the list. The test catches new state tabs only.
- Formulas in the app-written tabs (they are stored as values; the app writes plain values there).
- Secrets and settings in Vercel and GitHub, the server's `.env`, Telegram and mail provider settings.
- Files outside the database and the sheets (uploaded documents, the private data cache on the server).
- Changes made between two nightly runs: up to 24 hours of work can be lost.

## Not measured yet

- Recovery time: nobody has timed a full restore of the Sheets state or of the server. No target has been agreed.
- A write-back into Google Sheets has never been rehearsed against Google: the restore drill exists but has not run.
- The first real run of the Sheets steps (duration, Google read quota, size of the encrypted file).
