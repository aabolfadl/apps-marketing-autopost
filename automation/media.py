"""Turns a post's PNGs into the JPEGs Instagram accepts and puts them at public URLs.

Instagram's API only takes JPEG, and only by URL: Meta downloads each image itself. The JPEGs are
committed under media/ and served from raw.githubusercontent.com, pinned to the exact commit.
"""

import hashlib
import os
import re
import subprocess
import time
from io import BytesIO
from urllib.parse import quote

import requests
from PIL import Image

from store import ROOT, read_json, write_json

MEDIA_DIR = ROOT / "media"
MANIFEST = MEDIA_DIR / "manifest.json"
JPEG_QUALITY = 95
MAX_BYTES = 8 * 1024 * 1024  # Instagram's per-image limit


def jpegs_for(post):
    """Full-size JPEG copies of the post's images, reusing earlier conversions whose source is unchanged."""
    manifest = read_json(MANIFEST, {})
    out = []
    for src in post.images:
        key = src.relative_to(ROOT).as_posix()
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        dst = MEDIA_DIR / post.app / post.name / f"{src.stem}.jpg"
        if manifest.get(key) != digest or not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(src) as im:
                # Same pixel size as the original, no resizing. 4:4:4 chroma keeps coloured text crisp,
                # which matters because Instagram recompresses whatever it receives.
                flatten(im).save(dst, "JPEG", quality=JPEG_QUALITY, subsampling=0, optimize=True)
            if dst.stat().st_size > MAX_BYTES:
                raise RuntimeError(f"{dst.name} is over Instagram's 8 MB limit as a JPEG")
            manifest[key] = digest
        out.append(dst)
    write_json(MANIFEST, manifest)
    return out


def flatten(im):
    """RGB with any transparency composited onto white, since JPEG has no alpha channel."""
    if im.mode in ("RGBA", "LA") or "transparency" in im.info:
        rgba = im.convert("RGBA")
        background = Image.new("RGB", im.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return im.convert("RGB")


def pixel_size(url):
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    with Image.open(BytesIO(response.content)) as im:
        return im.size


def git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _relative(paths):
    return [p.relative_to(ROOT).as_posix() for p in paths if p.exists()]


def has_changes(paths):
    existing = _relative(paths)
    return bool(existing) and bool(git("status", "--porcelain", "--", *existing))


def commit_and_push(paths, message):
    """Commits whatever changed under `paths` and pushes it. Returns False when nothing had changed."""
    existing = _relative(paths)
    if not existing:
        return False
    git("add", "--", *existing)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return False
    git("commit", "-m", message)
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    for attempt in range(3):
        try:
            git("push", "origin", "HEAD")
            return True
        except RuntimeError:
            if attempt == 2:
                raise
            # Someone pushed in the meantime (for example a manual edit); replay on top of it.
            git("pull", "--rebase", "--autostash", "origin", branch)
    return True


def repo_slug():
    slug = os.environ.get("GITHUB_REPOSITORY")
    if slug:
        return slug
    url = git("remote", "get-url", "origin")
    match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if not match:
        raise RuntimeError(f"the origin remote ({url}) is not a GitHub repository")
    return match.group(1)


def public_urls(paths):
    sha = git("rev-parse", "HEAD")
    slug = repo_slug()
    return [f"https://raw.githubusercontent.com/{slug}/{sha}/{quote(p.relative_to(ROOT).as_posix())}" for p in paths]


def wait_until_public(urls, timeout=180):
    """Meta fetches the images itself, so make sure it will find them before asking it to."""
    deadline = time.monotonic() + timeout
    pending = list(urls)
    while True:
        pending = [u for u in pending if requests.head(u, timeout=30).status_code != 200]
        if not pending:
            return
        if time.monotonic() > deadline:
            raise RuntimeError(
                f"{len(pending)} image(s) are not publicly reachable, for example {pending[0]}. "
                "The GitHub repository must be public and pushed."
            )
        time.sleep(5)
