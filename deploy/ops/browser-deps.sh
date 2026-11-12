#!/usr/bin/env bash
# System libraries the stealth browser (Scrapling -> Playwright/Patchright Chromium) needs on the company server.
# Playwright's bundled node fails with "libatomic.so.1: cannot open shared object file" without libatomic1 (found
# 12 Nov 2026: Bahrain DOWN since 9 Nov, every stealth probe failed). Installs the Ubuntu 24.04 package names.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot sh -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq --no-install-recommends \
  libatomic1 libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
  libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64 fonts-liberation >/dev/null 2>&1; \
  dpkg -l libatomic1 libnss3 libgbm1 2>/dev/null | grep "^ii" | awk "{print \$2, \$3}"'
echo "browser deps installed"
