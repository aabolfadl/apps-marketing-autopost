"""The post folders: what exists, what is already posted, and whether a post is publishable as is."""

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from store import ROOT

POSTED_FILE = "already-posted.txt"
POST_FOLDER = re.compile(r"^(\d+)-")
IMAGE_NAME = re.compile(r"^(\d+)\.(png|jpe?g)$", re.IGNORECASE)
HASHTAG = re.compile(r"(?<!\w)#\w+")
MENTION = re.compile(r"(?<![\w.])@[\w.]+")

# Instagram's limits for feed posts published through the API.
MAX_IMAGES = 10
MAX_CAPTION = 2200
MAX_HASHTAGS = 30
MAX_MENTIONS = 20
MIN_WIDTH = 320
TALLEST = 4 / 5  # width / height. Anything taller gets cropped or rejected.
WIDEST = 1.91


@dataclass
class Post:
    app: str
    folder: Path

    @property
    def name(self):
        return self.folder.name

    @property
    def number(self):
        return POST_FOLDER.match(self.folder.name).group(1)

    @property
    def images(self):
        found = [p for p in self.folder.iterdir() if p.is_file() and IMAGE_NAME.match(p.name)]
        return sorted(found, key=lambda p: int(IMAGE_NAME.match(p.name).group(1)))

    def caption(self):
        text = (self.folder / "caption.txt").read_text(encoding="utf-8-sig")
        return text.replace("\r\n", "\n").strip()


def posts(app):
    folders = [p for p in (ROOT / app).iterdir() if p.is_dir() and POST_FOLDER.match(p.name)]
    folders.sort(key=lambda p: (int(POST_FOLDER.match(p.name).group(1)), p.name))
    return [Post(app, f) for f in folders]


def posted_file(app):
    return ROOT / app / POSTED_FILE


def posted_numbers(app):
    path = posted_file(app)
    if not path.exists():
        return set()
    return {int(word) for word in path.read_text(encoding="utf-8-sig").split() if word.isdigit()}


def mark_posted(app, number):
    path = posted_file(app)
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(f"{text}{number}\n", encoding="utf-8")


def remaining(app):
    done = posted_numbers(app)
    return [p for p in posts(app) if int(p.number) not in done]


def find(app, number):
    return next((p for p in posts(app) if int(p.number) == int(number)), None)


def problems(post):
    """Everything that would stop this post going out at full size. Empty means publishable."""
    images = post.images
    if not images:
        return ["no numbered images (01.png, 02.png, ...)"]
    issues = []

    numbers = [int(IMAGE_NAME.match(p.name).group(1)) for p in images]
    if numbers != list(range(1, len(numbers) + 1)):
        issues.append(f"images should be numbered 1 to {len(numbers)} with no gaps, found {', '.join(p.name for p in images)}")
    if len(images) > MAX_IMAGES:
        issues.append(f"{len(images)} images, Instagram's API allows {MAX_IMAGES} per carousel")

    sizes = set()
    for path in images:
        with Image.open(path) as im:
            sizes.add(im.size)
    if len(sizes) > 1:
        listed = ", ".join(f"{w}x{h}" for w, h in sorted(sizes))
        issues.append(f"images differ in size ({listed}); Instagram crops every slide to the first slide's shape")
    for width, height in sizes:
        if not TALLEST - 0.005 <= width / height <= WIDEST + 0.005:
            issues.append(f"{width}x{height} is outside Instagram's 4:5 to 1.91:1 range and would be cropped")
        if width < MIN_WIDTH:
            issues.append(f"{width}px wide, below Instagram's {MIN_WIDTH}px minimum")

    if not (post.folder / "caption.txt").exists():
        issues.append("no caption.txt")
        return issues
    caption = post.caption()
    if not caption:
        issues.append("caption.txt is empty")
    if len(caption) > MAX_CAPTION:
        issues.append(f"caption is {len(caption)} characters, the limit is {MAX_CAPTION}")
    if len(HASHTAG.findall(caption)) > MAX_HASHTAGS:
        issues.append(f"caption has {len(HASHTAG.findall(caption))} hashtags, the limit is {MAX_HASHTAGS}")
    if len(MENTION.findall(caption)) > MAX_MENTIONS:
        issues.append(f"caption has {len(MENTION.findall(caption))} @mentions, the limit is {MAX_MENTIONS}")
    return issues
