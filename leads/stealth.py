"""Scrapling helper for portals that only render in a real browser. Installs itself on first use (runner has no browser)."""
import subprocess
import sys

from .common import log


def fetcher():
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        log.info("installing scrapling")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "scrapling[fetchers]"], check=False)
        subprocess.run(["scrapling", "install"], check=False, timeout=900)
        from scrapling.fetchers import StealthyFetcher
    return StealthyFetcher


def html(url, wait=True, timeout=90000):
    p = fetcher().fetch(url, headless=True, network_idle=wait, timeout=timeout)
    return p.html_content if p.status == 200 else ""
