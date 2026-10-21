#!/usr/bin/env python3
"""Publishes the post folders to Instagram (and Facebook Pages) on the schedule in config.json.

    python automation/poster.py check                       validate every unposted post
    python automation/poster.py plan [--write]              upcoming calendar (--write updates SCHEDULE.md)
    python automation/poster.py run [--dry-run]             publish whatever is due now (GitHub Actions runs this)
    python automation/poster.py status                      check every token and account
    python automation/poster.py post-now APP [--number NN]  publish the next (or a given) post immediately
    python automation/poster.py retry-facebook APP --number NN
    python automation/poster.py add-instagram APP           save an Instagram token (local, one-time)
    python automation/poster.py add-facebook                save Facebook Page tokens (local, optional)
    python automation/poster.py refresh                     renew the Instagram tokens now
    python automation/poster.py init-key                    create the local encryption key

SETUP.md has the one-time setup.
"""

import argparse
import getpass
import os
import sys
from datetime import datetime, timedelta
from math import gcd

import requests
from PIL import Image

import content
import media
import meta
import store
from schedule import Plan

SCHEDULE_FILE = store.ROOT / "SCHEDULE.md"
REFRESH_EVERY = timedelta(days=7)
REFRESH_URGENT = timedelta(days=14)
IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"


def say(message):
    print(message, flush=True)


def warn(message):
    print(f"::warning::{message}" if IN_CI else f"WARNING: {message}", flush=True)


def fail(message):
    print(f"::error::{message}" if IN_CI else f"ERROR: {message}", flush=True)


def load():
    config = store.load_config()
    plan = Plan(config)
    issues = plan.problems()
    if issues:
        raise SystemExit("config.json: " + "; ".join(issues))
    return config, plan


def resolve_app(config, name):
    match = next((app for app in config["apps"] if app.lower() == name.lower()), None)
    if not match:
        raise SystemExit(f"Unknown app {name!r}. Expected one of: {', '.join(config['apps'])}")
    return match


def stamp(moment):
    return moment.isoformat(timespec="seconds")


# Publishing -----------------------------------------------------------------------------------


def publish_post(config, plan, app, post, tokens, log, slot=None):
    """Publishes one post to Instagram, then Facebook if a Page is connected, and records it.

    `slot` is the scheduled time it is going out for; manual posts have none.
    """
    issues = content.problems(post)
    if issues:
        raise RuntimeError("not publishable: " + "; ".join(issues))
    account = tokens.get(app, "instagram")
    caption = post.caption()
    ig = meta.Instagram(config["graph_api_version"], account["token"])

    jpegs = media.jpegs_for(post)
    media.commit_and_push([media.MEDIA_DIR], f"Images for {app} {post.name}")
    urls = media.public_urls(jpegs)

    existing = ig.find_by_caption(account["user_id"], caption)
    if existing:
        warn(f"{app}: {post.name} is already on Instagram ({existing.get('permalink')}), recording it instead of posting again")
        media_id, permalink = existing["id"], existing.get("permalink")
    else:
        say(f"{app}: publishing {post.name} ({len(urls)} image{'s' if len(urls) > 1 else ''}) to @{account['username']}")
        media.wait_until_public(urls)
        media_id, permalink = ig.publish(account["user_id"], urls, caption, say), None

    entry = {
        "app": app,
        "post": post.name,
        "posted_at": stamp(plan.now()),
        "slot": stamp(slot) if slot else None,
        "instagram": {"media_id": media_id, "permalink": permalink},
        "facebook": None,
    }
    # Record it before anything else can fail, so a later error never leads to a second copy.
    content.mark_posted(app, post.number)
    log.add(entry)
    log.save()
    if not permalink:
        try:
            permalink = entry["instagram"]["permalink"] = ig.media(media_id).get("permalink")
        except meta.MetaError as e:
            warn(f"{app}: published, but could not look up the link: {e}")
    say(f"{app}: live on Instagram at {permalink or media_id}")

    entry["instagram"]["size_check"] = check_full_size(ig, media_id, jpegs[0])
    log.save()
    publish_to_facebook(config, app, post, tokens, entry, urls, caption)
    log.save()


def check_full_size(ig, media_id, original):
    """Downloads what Instagram is actually serving and compares its shape with the original."""
    with Image.open(original) as im:
        width, height = im.size
    divisor = gcd(width, height)
    shape = f"{width // divisor}:{height // divisor}"
    try:
        served = [media.pixel_size(url) for url in ig.image_urls(media_id)]
    except (meta.MetaError, requests.RequestException, OSError) as e:
        warn(f"could not verify the published size: {e}")
        return "not checked"
    if not served:
        warn("could not verify the published size: Instagram returned no image URLs")
        return "not checked"
    cropped = [f"slide {i}: {w}x{h}" for i, (w, h) in enumerate(served, 1) if abs(w / h - width / height) > 0.01]
    if cropped:
        warn(f"Instagram is showing some slides in a different shape from the {shape} originals ({', '.join(cropped)}). Check the post.")
        return "shape changed: " + ", ".join(cropped)
    say(f"  full-size check passed: {len(served)} slide(s) served at {served[0][0]}x{served[0][1]}, {shape} kept")
    return f"ok, {shape} at {served[0][0]}x{served[0][1]}"


def publish_to_facebook(config, app, post, tokens, entry, urls, caption):
    page = tokens.get(app, "facebook")
    if not page:
        return
    fb = meta.FacebookPage(config["graph_api_version"], page["page_id"], page["token"])
    try:
        existing = fb.find_by_caption(caption)
        if existing:
            warn(f"{app}: {post.name} is already on Facebook, recording it instead of posting again")
            entry["facebook"] = {"post_id": existing["id"], "permalink": existing.get("permalink_url")}
            return
        post_id = fb.publish(urls, caption)
    except meta.MetaError as e:
        entry["facebook"] = {"error": str(e)}
        raise RuntimeError(
            f"the Instagram post is live but Facebook failed: {e}. "
            f"Retry with: retry-facebook {app} --number {post.number}"
        ) from e
    try:
        permalink = fb.permalink(post_id)
    except meta.MetaError:
        permalink = None
    entry["facebook"] = {"post_id": post_id, "permalink": permalink}
    say(f"{app}: live on Facebook at {permalink or post_id}")


def refresh_tokens(config, plan, tokens, force=False):
    """Renews Instagram tokens weekly so they never reach their 60-day expiry. Returns problems worth failing on."""
    problems = []
    renewed = False
    now = plan.now()
    for app in config["apps"]:
        account = tokens.get(app, "instagram")
        if not account:
            continue
        saved = datetime.fromisoformat(account["saved_at"])
        if now - saved < (timedelta(days=1) if force else REFRESH_EVERY):
            continue
        try:
            result = meta.refresh_instagram_token(account["token"])
        except meta.MetaError as e:
            expires = datetime.fromisoformat(account["expires_at"])
            message = f"{app}: could not renew the Instagram token ({e}). It expires {expires:%d %b %Y}."
            if expires - now < REFRESH_URGENT:
                problems.append(message)
                fail(message)
            else:
                warn(message)
            continue
        account.update(
            token=result["access_token"],
            saved_at=stamp(now),
            expires_at=stamp(now + timedelta(seconds=int(result.get("expires_in", 60 * 86400)))),
        )
        tokens.put(app, "instagram", account)
        renewed = True
        say(f"{app}: Instagram token renewed, now valid until {account['expires_at'][:10]}")
    if renewed:
        tokens.save()
    return problems


def state_paths(config):
    return [store.TOKENS_FILE, store.LOG_FILE, SCHEDULE_FILE] + [content.posted_file(app) for app in config["apps"]]


def save_state(config, plan, message):
    """Commits and pushes the post log, already-posted lists, tokens and SCHEDULE.md if any of them changed."""
    if not media.has_changes(state_paths(config)):
        return
    write_schedule(config, plan)
    media.commit_and_push(state_paths(config), message)


def push_tokens(message):
    try:
        if media.commit_and_push([store.TOKENS_FILE], message):
            say("Pushed automation/tokens.json to GitHub (the token inside is encrypted).")
    except RuntimeError as e:
        warn(f"saved locally but not pushed ({e}). Run `git push` once the GitHub repository is set up.")


# Schedule -------------------------------------------------------------------------------------


def projection(config, plan):
    log = store.PostLog()
    now = plan.now()
    rows = []
    for app in config["apps"]:
        if plan.enabled(app):
            last = log.last_day(app, plan.tz)
            rows += [(when, app, post) for when, post in plan.project(app, content.remaining(app), now, last)]
    rows.sort(key=lambda row: row[0])
    return rows


def write_schedule(config, plan):
    rows = projection(config, plan)
    log = store.PostLog()
    lines = [
        "# Posting schedule",
        "",
        f"Projected on {plan.now():%A %d %B %Y}, Cairo time. Updated automatically after every post.",
        "",
        f"Each app posts on one day, rests {plan.cycle - 1}, then posts again. "
        "If a posting day is missed, that app's remaining posts move to its next posting day.",
        "",
        "| App | Account | Time (Cairo) | Posts left | Last automated post | Final post |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for app, conf in config["apps"].items():
        mine = [when for when, a, _ in rows if a == app]
        last = log.last_day(app, plan.tz)
        status = "paused" if not plan.enabled(app) else (f"{mine[-1]:%a %d %b %Y}" if mine else "done")
        lines.append(
            f"| {app} | @{conf['instagram']} | {conf['time']} | {len(content.remaining(app))} | "
            f"{f'{last:%a %d %b %Y}' if last else 'none yet'} | {status} |"
        )
    lines += ["", "| Date | Day | Time (Cairo) | App | Post |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {when:%Y-%m-%d} | {when:%a} | {when:%H:%M} | {app} | {post.name} |" for when, app, post in rows]
    SCHEDULE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Commands -------------------------------------------------------------------------------------


def cmd_check(args):
    config, plan = load()
    errors = 0
    for app in config["apps"]:
        posts = content.posts(app)
        numbers = [int(p.number) for p in posts]
        for number in sorted({n for n in numbers if numbers.count(n) > 1}):
            fail(f"{app}: more than one folder is numbered {number:02d}")
            errors += 1
        for number in sorted(content.posted_numbers(app) - set(numbers)):
            warn(f"{app}: already-posted.txt lists {number:02d}, but there is no folder with that number")
        left = content.remaining(app)
        for post in left:
            for issue in content.problems(post):
                fail(f"{app}/{post.name}: {issue}")
                errors += 1
        images = sum(len(p.images) for p in left)
        say(f"{app}: {len(posts)} posts, {len(posts) - len(left)} already posted, {len(left)} to go ({images} images)")
    if errors:
        raise SystemExit(f"{errors} problem(s) found.")
    say("Everything left to post is publishable at full size.")


def cmd_plan(args):
    config, plan = load()
    for when, app, post in projection(config, plan):
        say(f"{when:%a %Y-%m-%d %H:%M}  {app:<8} {post.name}")
    if args.write:
        write_schedule(config, plan)
        say(f"Wrote {SCHEDULE_FILE.name}")


def cmd_run(args):
    config, plan = load()
    tokens, log = store.Tokens(), store.PostLog()
    now = plan.now()
    say(f"Cairo time {now:%a %d %b %Y %H:%M}")
    failures = [] if args.dry_run else refresh_tokens(config, plan, tokens)
    published = []
    for app in config["apps"]:
        due, reason = plan.due(app, now, log.last_day(app, plan.tz))
        if not due:
            say(f"{app}: {reason}")
            continue
        post = next(iter(content.remaining(app)), None)
        if post is None:
            say(f"{app}: every post is published")
            continue
        if args.dry_run:
            say(f"{app}: due, would publish {post.name}")
            continue
        if not tokens.get(app, "instagram"):
            warn(f"{app}: {post.name} is due but Instagram is not connected yet (see SETUP.md)")
            continue
        try:
            publish_post(config, plan, app, post, tokens, log, slot=plan.slot(app, now.date()))
            published.append(f"{app} {post.number}")
        except (meta.MetaError, RuntimeError, requests.RequestException, OSError) as e:
            failures.append(f"{app} {post.name}: {e}")
            fail(f"{app} {post.name}: {e}")
    if not args.dry_run:
        try:
            save_state(config, plan, f"Posted {', '.join(published)}" if published else "Renew tokens")
        except RuntimeError as e:
            failures.append(f"saving state: {e}")
            fail(f"saving state: {e}")
    if failures:
        raise SystemExit(1)


def cmd_post_now(args):
    config, plan = load()
    app = resolve_app(config, args.app)
    tokens, log = store.Tokens(), store.PostLog()
    if args.number:
        post = content.find(app, args.number)
        if not post:
            raise SystemExit(f"{app} has no post numbered {args.number}")
        if int(post.number) in content.posted_numbers(app):
            raise SystemExit(f"{app} {post.name} is already in already-posted.txt")
    else:
        post = next(iter(content.remaining(app)), None)
        if not post:
            raise SystemExit(f"{app} has nothing left to post")
    last = log.last_day(app, plan.tz)
    if last and (plan.now().date() - last).days < plan.cycle:
        warn(f"{app} last posted {last:%a %d %b}; posting now breaks its {plan.cycle - 1}-day rest")
    if args.dry_run:
        say(f"Would publish {app} {post.name} now")
        return
    if not tokens.get(app, "instagram"):
        raise SystemExit(f"Instagram is not connected for {app} yet (see SETUP.md)")
    try:
        publish_post(config, plan, app, post, tokens, log)
    finally:
        save_state(config, plan, f"Posted {app} {post.number} (manual)")


def cmd_retry_facebook(args):
    config, plan = load()
    app = resolve_app(config, args.app)
    tokens, log = store.Tokens(), store.PostLog()
    post = content.find(app, args.number)
    entry = log.find(app, post.name) if post else None
    if not entry:
        raise SystemExit(f"No automated post {args.number} for {app} in the post log")
    if not tokens.get(app, "facebook"):
        raise SystemExit(f"No Facebook Page is connected for {app}")
    urls = media.public_urls(media.jpegs_for(post))
    media.wait_until_public(urls)
    try:
        publish_to_facebook(config, app, post, tokens, entry, urls, post.caption())
    finally:
        log.save()
        save_state(config, plan, f"Posted {app} {post.number} to Facebook")


def cmd_status(args):
    config, plan = load()
    tokens, log = store.Tokens(), store.PostLog()
    version = config["graph_api_version"]
    now = plan.now()
    for app, conf in config["apps"].items():
        say(f"{app} (@{conf['instagram']})")
        account = tokens.get(app, "instagram")
        if not account:
            say("  Instagram: not connected")
        else:
            try:
                ig = meta.Instagram(version, account["token"])
                me = ig.me()
                quota = ig.publishing_quota(account["user_id"])
                say(
                    f"  Instagram: connected as @{me['username']}, token valid until {account['expires_at'][:10]}, "
                    f"{quota.get('quota_usage', '?')} API posts in the last 24h"
                )
                if me["username"].lower() != conf["instagram"].lower():
                    fail(f"  the token is for @{me['username']}, but config.json says @{conf['instagram']}")
            except meta.MetaError as e:
                fail(f"  Instagram: {e}")
        page = tokens.get(app, "facebook")
        if not page:
            say("  Facebook: not connected")
        else:
            try:
                say(f"  Facebook: {meta.FacebookPage(version, page['page_id'], page['token']).name()}")
            except meta.MetaError as e:
                fail(f"  Facebook: {e}")
        upcoming = plan.project(app, content.remaining(app)[:1], now, log.last_day(app, plan.tz))
        if upcoming:
            when, post = upcoming[0]
            say(f"  next: {post.name} on {when:%a %d %b %H:%M}")
        else:
            say("  next: nothing left")


def cmd_add_instagram(args):
    config, plan = load()
    app = resolve_app(config, args.app)
    handle = config["apps"][app]["instagram"]
    token = getpass.getpass(f"Paste the Instagram access token for @{handle} (it stays hidden), then press Enter: ").strip()
    if not token:
        raise SystemExit("No token entered. Nothing saved.")
    ig = meta.Instagram(config["graph_api_version"], token)
    try:
        me = ig.me()
    except meta.MetaError as e:
        raise SystemExit(f"Instagram did not accept that token: {e}")
    if me.get("username", "").lower() != handle.lower():
        raise SystemExit(f"That token belongs to @{me.get('username')}, not @{handle}. Nothing saved.")
    user_id = str(me.get("user_id") or me["id"])
    try:
        ig.publishing_quota(user_id)
    except meta.MetaError as e:
        raise SystemExit(
            f"The token works but cannot publish ({e}). Give the app the instagram_business_content_publish "
            "permission (SETUP.md, step 2.3), generate the token again and retry."
        )
    tokens = store.Tokens()
    now = plan.now()
    tokens.put(app, "instagram", {
        "user_id": user_id,
        "username": me["username"],
        "saved_at": stamp(now),
        "expires_at": stamp(now + timedelta(days=60)),
        "token": token,
    })
    tokens.save()
    say(f"Connected @{me['username']} for {app}. It can publish.")
    push_tokens(f"Connect Instagram for {app}")


def cmd_add_facebook(args):
    config, plan = load()
    version = config["graph_api_version"]
    app_id = input("Meta App ID: ").strip()
    app_secret = getpass.getpass("Meta App secret (hidden): ").strip()
    short_token = getpass.getpass("User access token from Graph API Explorer (hidden): ").strip()
    try:
        user_token = meta.long_lived_user_token(version, app_id, app_secret, short_token)
        pages = meta.managed_pages(version, user_token)
    except meta.MetaError as e:
        raise SystemExit(f"Meta refused: {e}")
    if not pages:
        raise SystemExit("That token sees no Pages. Make sure you ticked every Page when Facebook asked which ones to allow.")
    say("Pages this token can manage:")
    for i, page in enumerate(pages, 1):
        say(f"  {i}. {page['name']}")
    tokens = store.Tokens()
    for app in config["apps"]:
        guess = next((p for p in pages if app.lower() in p["name"].lower()), None)
        hint = f"Enter = {guess['name']}, 0 = none" if guess else "Enter = none"
        answer = input(f"Page for {app}? [number, {hint}]: ").strip()
        if answer == "":
            page = guess
        elif answer == "0":
            page = None
        elif answer.isdigit() and 1 <= int(answer) <= len(pages):
            page = pages[int(answer) - 1]
        else:
            raise SystemExit(f"{answer!r} is not one of the numbers above. Nothing saved.")
        if not page:
            continue
        expires = meta.token_expiry(version, page["access_token"], app_id, app_secret)
        tokens.put(app, "facebook", {
            "page_id": page["id"],
            "page_name": page["name"],
            "saved_at": stamp(plan.now()),
            "expires_at": "never" if not expires else stamp(datetime.fromtimestamp(expires, plan.tz)),
            "token": page["access_token"],
        })
        say(f"  {app} -> {page['name']} ({'token never expires' if not expires else 'token expires ' + str(datetime.fromtimestamp(expires).date())})")
    tokens.save()
    push_tokens("Connect Facebook Pages")


def cmd_refresh(args):
    config, plan = load()
    tokens = store.Tokens()
    problems = refresh_tokens(config, plan, tokens, force=True)
    push_tokens("Renew Instagram tokens")
    if problems:
        raise SystemExit(1)


def cmd_init_key(args):
    if store.create_key():
        say(f"Created {store.KEY_FILE}. Copy its contents into a GitHub secret named TOKENS_KEY. Keep it private.")
    else:
        say(f"{store.KEY_FILE} already exists. Not touching it.")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check").set_defaults(func=cmd_check)
    plan = commands.add_parser("plan")
    plan.add_argument("--write", action="store_true")
    plan.set_defaults(func=cmd_plan)
    run = commands.add_parser("run")
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(func=cmd_run)
    commands.add_parser("status").set_defaults(func=cmd_status)
    post_now = commands.add_parser("post-now")
    post_now.add_argument("app")
    post_now.add_argument("--number")
    post_now.add_argument("--dry-run", action="store_true")
    post_now.set_defaults(func=cmd_post_now)
    retry = commands.add_parser("retry-facebook")
    retry.add_argument("app")
    retry.add_argument("--number", required=True)
    retry.set_defaults(func=cmd_retry_facebook)
    add_ig = commands.add_parser("add-instagram")
    add_ig.add_argument("app")
    add_ig.set_defaults(func=cmd_add_instagram)
    commands.add_parser("add-facebook").set_defaults(func=cmd_add_facebook)
    commands.add_parser("refresh").set_defaults(func=cmd_refresh)
    commands.add_parser("init-key").set_defaults(func=cmd_init_key)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
