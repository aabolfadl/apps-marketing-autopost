# Make posts go out on time

GitHub's built-in timer is best effort. When GitHub is busy it runs scheduled workflows hours late or skips them. In the first week it ran 2 or 3 times a day instead of 24, and never at 20:00. That's why posts were late, and why Cents (19 Oct) and Lckdin (20 Oct) didn't post at all.

The fix is a free service, **cron-job.org**. At exactly 20:00 and 21:30 Cairo time, it clicks **Run workflow** for you. Setup takes about 10 minutes and you only do it once.

Do Part 1, then Part 2. Before 21:30 Cairo is best, so Pico's post tonight goes out on time.

---

## Part 1: Create a GitHub token that can only start the poster

1. Go to https://github.com/settings/personal-access-tokens/new (you may need to sign in).
2. **Token name:** `cron-job.org trigger`
3. **Expiration:** choose **No expiration** if it's offered. Otherwise pick the longest option, and put a reminder in your calendar a week before that date (see "Renewing the token" at the end).
4. **Repository access:** choose **Only select repositories**, then pick `aabolfadl/apps-marketing-autopost`.
5. **Permissions:** give it **Actions: Read and write** and nothing else.
   - If you see a list called **Repository permissions**, open it, find **Actions**, and change **No access** to **Read and write**.
   - If you see an **Add permissions** button instead, click it, tick **Actions**, then change its access from **Read-only** to **Read and write**.
   - **Metadata: Read-only** gets added on its own. That's expected.
6. Click **Generate token**, check the summary, and confirm.
7. **Copy the token now.** It starts with `github_pat_`, and GitHub will never show it again. Keep it somewhere private until Part 2 is done.

All this token can do is start or cancel workflow runs in that one repository. It can't read your code or change your posts.

---

## Part 2: Set up the cron-job.org timer

### 2.1 Make an account

1. Go to https://cron-job.org and click **Sign up**. It's free.
2. Confirm your email address using the link they send you, then log in.

### 2.2 Create the job

Click **Cronjobs** in the menu, then **Create cronjob**.

**On the COMMON tab:**

| Field | Value |
| --- | --- |
| Title | `Post to Instagram` |
| URL | `https://api.github.com/repos/aabolfadl/apps-marketing-autopost/actions/workflows/post.yml/dispatches` |
| Enable job | on |
| Save responses in job history | on (this helps if something goes wrong) |

**Execution schedule:** choose **Custom**, then set:

- **Days of month:** every day
- **Days of week:** every day
- **Months:** every month
- **Hours:** `20`, `21`, `22` (hold Ctrl to select more than one)
- **Minutes:** `0` and `30`

If you see one **Crontab expression** box instead, type `0,30 20-22 * * *`.

That gives runs at 20:00, 20:30, 21:00, 21:30, 22:00 and 22:30. The 20:00 and 21:30 runs post. The others only do something if an on-time run failed; otherwise they finish in a few seconds without doing anything.

**On the ADVANCED tab:**

1. Under **Headers**, click **Add** three times and fill in:

   | Key | Value |
   | --- | --- |
   | `Authorization` | `Bearer ` followed by your token, for example `Bearer github_pat_11ABC...` (there's one space after `Bearer`) |
   | `Accept` | `application/vnd.github+json` |
   | `Content-Type` | `application/json` |

2. **Time zone:** `Africa/Cairo`. This matters: it makes the job follow Cairo's switch to winter time (the night of 29 October) without you changing anything.
3. **Request method:** `POST`
4. **Request body:**

   ```json
   {"ref":"main"}
   ```

5. Leave everything else as it is.

**On the NOTIFICATIONS tab** (optional): turn on the email for when the job fails.

### 2.3 Test it, then save

1. Click **TEST RUN**, then start the test.
2. You should see a status of **200** or **204**. Both mean GitHub accepted it.
   - **401**: the token is wrong, or `Bearer ` is missing in front of it.
   - **403** or **404**: the token doesn't have **Actions: Read and write**, or `apps-marketing-autopost` wasn't selected under repository access. Fix it in Part 1 (you can edit the token, you don't need a new one).
   - **422**: the request body isn't exactly `{"ref":"main"}`.
3. On GitHub, open the repository's **Actions** tab. There's a new **Post to Instagram** run, marked **Manually run by aabolfadl**. It finishes in about 20 seconds. That label is normal: cron-job.org is using your token.

   The test is a real run. If an app's slot is open right then (between its posting time and 2.5 hours later, on its posting day), it posts. That's what should happen anyway.

4. Close the test window and click **CREATE** (or **SAVE**).

---

## Part 3: Check after the next slot

Tonight Pico posts at 21:30. At about 21:32:

- GitHub **Actions** shows a run that started at 21:30, marked **Manually run by aabolfadl**.
- The post is live on @pico.puzzles.
- On cron-job.org, the job's history shows the 21:30 run as successful.

---

## Good to know

- **GitHub's own timer stays on as a backup.** If cron-job.org ever fails, GitHub may still post late, up to 2.5 hours after the slot, the same as before.
- **Changing a posting time:** if you edit `"time"` in `automation/config.json`, also add the new hour and minute to this job's schedule on cron-job.org.
- **Pausing:** disabling the workflow on GitHub (**Actions** → **Post to Instagram** → **⋯** → **Disable workflow**) still stops everything. cron-job.org will then show errors, so pause the cron-job.org job as well.
- **Renewing the token:** if your token has an expiry date, GitHub emails you about a week before it runs out. Create a new one (Part 1), then on cron-job.org edit the job, change the `Authorization` header to `Bearer ` plus the new token, and save.
