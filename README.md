# Apps marketing autopost

Publishes ready-made carousel posts for four iOS apps (Cents, Lckdin, Pico, Trivial) to Instagram, and to each app's Facebook Page, on a fixed schedule in Cairo time. It runs on GitHub Actions, so no computer needs to stay on.

- First-time setup: [SETUP.md](SETUP.md)
- Making posts go out on the minute (cron-job.org trigger): [ON-TIME-POSTING.md](ON-TIME-POSTING.md)
- What's coming next: [SCHEDULE.md](SCHEDULE.md), regenerated after every post

## Layout

```
Cents/ Lckdin/ Pico/ Trivial/      the posts, one numbered folder each: 01.png, 02.png, ... + caption.txt
  already-posted.txt               post numbers that are done (by the bot or by hand)
media/                             JPEG copies Instagram downloads (generated, committed by the bot)
automation/
  poster.py                        command-line entry point (check, plan, run, status, post-now, ...)
  schedule.py                      which app posts on which day and time
  content.py                       finds posts and checks them against Instagram's limits
  media.py                         PNG to JPEG, git commit/push, public raw.githubusercontent URLs
  meta.py                          Instagram and Facebook Graph API calls
  store.py                         config, the encrypted token store, the post log
  config.json                      apps, handles, posting times, cycle length, API version
  tokens.json                      access tokens, encrypted with the TOKENS_KEY secret
  post-log.json                    one entry per automated post
.github/workflows/post.yml         the GitHub Actions job
```

Not in git: `automation/.tokens-key` (the local copy of TOKENS_KEY), `automation/secrets/` (plain-text tokens), and working files such as `*/.clean/`, `*/POSTING_PLAN.md` and `*/index.html`.

## How a post goes out

1. **Trigger.** cron-job.org calls the workflow's `workflow_dispatch` at 20:00, 20:30, 21:00, 21:30, 22:00 and 22:30 Cairo time. GitHub's own `schedule` trigger stays on as a backup, but GitHub often runs it late or skips it.
2. **Is anything due?** `poster.py run` asks `schedule.Plan.due` about each app. An app posts on one day out of every `cycle_days` days (its `phase`, counted from `anchor_date`), at its `time`. It can still post up to `late_window_minutes` after that time, and never twice within one cycle.
3. **Images.** `media.py` converts the post's PNGs to full-size JPEGs, commits them under `media/`, pushes, and waits until their raw.githubusercontent.com URLs are reachable. Instagram fetches the images itself.
4. **Publish.** `meta.Instagram` creates the carousel and publishes it. It first looks for an existing post with the same caption, so a retry never posts twice. If a Page is connected, `meta.FacebookPage` then posts the same images and caption there.
5. **Record.** The post number goes into `already-posted.txt`, an entry goes into `post-log.json`, and SCHEDULE.md is regenerated. The bot commits and pushes all of it.

Instagram tokens are renewed weekly during runs, well before their 60-day expiry. Facebook Page tokens don't expire.

## Details worth knowing

- **`slot` in post-log.json** is the scheduled time a post went out for, and `posted_at` is when it actually went out. The rest-day rule uses `slot`, so a 21:30 post that goes out just after midnight still counts for its own day. Manual `post-now` posts have no slot and use `posted_at`.
- **`add-facebook` checks permissions before saving.** It refuses a token that lacks `pages_show_list`, `pages_manage_posts` or `pages_read_engagement`. Without those, every Instagram post would be followed by a failed Facebook post.
- **Pushing with local edits.** If someone pushed in the meantime, `media.commit_and_push` pulls with `--rebase --autostash` and tries again. Uncommitted edits in your working copy don't block it.

## Commands

Run these from this folder. Locally they need `automation/.tokens-key`; on GitHub they need the `TOKENS_KEY` secret.

```powershell
python automation/poster.py check            # every unposted post is publishable at full size
python automation/poster.py plan [--write]   # upcoming calendar (--write updates SCHEDULE.md)
python automation/poster.py run --dry-run    # what would post right now
python automation/poster.py status           # tokens, accounts, next post per app
```

`post-now`, `retry-facebook` and `refresh` are also available from **Actions → Post to Instagram → Run workflow**.
