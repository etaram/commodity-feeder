"""Scrapling helper for portals that only render in a real browser. Installs itself on first use (runner has no browser)."""
import subprocess
import sys

from .common import log


_READY = []


def _browsers_installed():
    """True when the Patchright/Playwright browser binaries are on disk (the pip package alone is not enough:
    Bahrain went DOWN on 9 Nov 2026 with 'patchright install' missing on a runner that had the package cached)."""
    import glob
    import os
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), os.path.expanduser("~/.cache/ms-playwright")]
    return any(r and glob.glob(os.path.join(r, "chromium*")) for r in roots)


def fetcher():
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        log.info("installing scrapling")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "scrapling[fetchers]"], check=False)
        from scrapling.fetchers import StealthyFetcher
    if not _READY and not _browsers_installed():
        log.info("installing the browser binaries (scrapling install)")
        subprocess.run(["scrapling", "install"], check=False, timeout=900)
        if not _browsers_installed():
            subprocess.run([sys.executable, "-m", "patchright", "install", "chromium"], check=False, timeout=900)
    _READY.append(1)
    return StealthyFetcher


def html(url, wait=True, timeout=90000):
    p = fetcher().fetch(url, headless=True, network_idle=wait, timeout=timeout)
    return p.html_content if p.status == 200 else ""


def pages(url, pages=10, next_sel='[rel="next"], button[wire\\:click*="nextPage"], a:has-text("Next"), button:has-text("Next"), a:has-text("\u203a"), button:has-text("\u203a"), a:has-text("Seterusnya")', timeout=120000):
    """Open `url` once in a browser and click "next" up to pages-1 times; returns the HTML after each step."""
    out = []

    def act(page):
        for i in range(pages):
            out.append(page.content())
            if i == pages - 1:
                break
            try:
                page.locator(next_sel).first.click(timeout=8000)
                page.wait_for_timeout(2500)
            except Exception as e:  # noqa: BLE001
                log.warning("pager stopped at %d: %s", i + 1, str(e)[:80]); break
        return page
    fetcher().fetch(url, headless=True, network_idle=True, timeout=timeout, page_action=act)
    return out
