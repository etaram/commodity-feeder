# sinder-relay
A one-function Vercel project deployed per region (sinder-relay-eu in fra1): collectors in GitHub Actions read
geoblocked portals through it. Secret and URL live in the Supplier Universe sheet, tab Config (RELAY_URL,
RELAY_SECRET), like WEB_INDEX_KEY; never in Git. Deployed from these files with the Vercel API (inline files).
