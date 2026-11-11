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

No tool in the repository writes a backup into Google Sheets. This is on purpose: a write-back replaces live data.
It is a separate step, done only after the owner approves it in writing, in this order:

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
- A full write-back into Google Sheets has never been rehearsed.
- The first real run of the Sheets steps (duration, Google read quota, size of the encrypted file).
