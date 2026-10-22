# One-time setup

Everything below is a one-off. When it's done, posts go out automatically from GitHub's servers and your PC can stay off. Plan on about 45 minutes, plus 15 more if you add Facebook.

Do the parts in order: **1 → 2 → 3 → 4**. Part 5 (Facebook) is optional and can wait.

Run every command in this guide in **VS Code's terminal (PowerShell)**, opened on the `Marketing\Social Media Posts` folder.

---

## Part 1: Make the 4 Instagram accounts professional

The posting API only works with Business or Creator accounts. Skip any account that already is one.

For each of `@cents.finance`, `@lckdinapp`, `@pico.puzzles`, `@trivial.app`:

1. In the Instagram app, open the account's profile.
2. Tap **☰** (top right), then **Settings and activity**, then **Account type and tools**, then **Switch to professional account**.
3. Pick a category (for example **App Page** or **Software**), then choose **Business**.
4. If it offers to connect a Facebook Page, tap **Skip**.

---

## Part 2: Put the project on GitHub

GitHub runs the posting on a timer and hosts the images at the public links Instagram downloads from.

### 2.1 Create the repository

1. Sign in at https://github.com (create a free account if you don't have one).
2. Go to https://github.com/new.
3. **Repository name:** `marketing-autopost` (any name works).
4. Choose **Public**. It has to be public so Instagram can fetch the images.
   - The repo will contain the post images and captions. They become public on Instagram anyway.
   - It will **not** contain the raw screenshots (`.clean`), `index.html` or `POSTING_PLAN.md`; those are excluded.
   - Access tokens are stored encrypted, and the key is never uploaded.
5. Leave "Add a README", ".gitignore" and "license" all **off**.
6. Click **Create repository**.

### 2.2 Upload the folder

In the VS Code terminal, run these one at a time. Replace `YOUR-USERNAME` with your GitHub username.

```powershell
git add .
git commit -m "Instagram auto-posting"
git remote add origin https://github.com/YOUR-USERNAME/marketing-autopost.git
git push -u origin main
```

A browser window may ask you to sign in to GitHub the first time; approve it. The upload is about 135 MB, so it can take a few minutes.

### 2.3 Give GitHub the encryption key

1. In VS Code, open `automation/.tokens-key`. It contains one line of text. Copy that whole line.
2. On GitHub, open your repository, then **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
3. **Name:** `TOKENS_KEY`
4. **Secret:** paste the line.
5. Click **Add secret**.

Never share or commit this key. If it's ever exposed, delete `automation/.tokens-key`, run `python automation/poster.py init-key`, update the secret, and redo step 3.7 for every account.

### 2.4 Switch on Actions

Open the repository's **Actions** tab. If GitHub says workflows are disabled, click the button to enable them.

---

## Part 3: Create the Meta app and connect the 4 Instagram accounts

### 3.1 Register as a Meta developer

1. Go to https://developers.facebook.com and log in with the Facebook account in the same Meta Accounts Center as your Instagram accounts.
2. If it's your first time, click **Get Started** and finish the short sign-up (it may ask you to verify your phone number or email).

### 3.2 Create the app

1. Click **My Apps** (top right), then **Create App**.
2. **App name:** `Marketing Autopost` (any name works). **Contact email:** your email. Click **Next**.
3. **Use case:** pick **Manage messaging & content on Instagram**. Click **Next**.
4. **Business:** pick **I don't want to connect a business portfolio yet**. Click **Next**.
5. Click **Create app** (Facebook may ask for your password).

### 3.3 Make sure the app can publish

1. In the app's left menu, click **Use cases**.
2. Next to the Instagram use case, click **Customize**.
3. Open **API setup with Instagram login**. In the **Permissions** list, make sure these two are added. Click **Add** next to any that isn't.
   - `instagram_business_basic`
   - `instagram_business_content_publish`

### 3.4 Add the 4 accounts as testers

1. In the left menu, click **App roles**, then **Roles**.
2. Click **Add People**, then choose **Instagram Tester**.
3. Type `cents.finance` and confirm.
4. Repeat for `lckdinapp`, `pico.puzzles` and `trivial.app`.

### 3.5 Accept the invites

Do this on a computer, once per account:

1. Log in to https://www.instagram.com as that account.
2. Go to https://www.instagram.com/accounts/manage_access/ (Settings → Website permissions → Apps and websites).
3. Open the **Tester invites** tab and click **Accept**.
4. Log out, log in as the next account, and repeat.

### 3.6 Generate a token for each account

1. Back in the Meta dashboard, go to **Use cases** → **Customize** (Instagram) → **API setup with Instagram login**.
2. Under **1. Generate access tokens**, click **Add account**. Log in as one of the Instagram accounts and allow access.
3. Repeat **Add account** for the other three. **Tip:** use a private or incognito browser window for each one so Instagram doesn't log you in as the previous account.
4. All 4 accounts now appear in the list.

### 3.7 Save each token (in VS Code)

For each account:

1. Click **Generate token** next to it in the dashboard, confirm any prompts, and **copy** the token. It's a long string.
2. In the VS Code terminal, run the matching command:

   ```powershell
   python automation/poster.py add-instagram Cents
   python automation/poster.py add-instagram Lckdin
   python automation/poster.py add-instagram Pico
   python automation/poster.py add-instagram Trivial
   ```

3. When it asks, paste the token (right-click or Ctrl+V) and press **Enter**. Nothing appears while you paste; that's normal.

Each command:

- checks that the token belongs to the right account (it refuses a Pico token for Cents),
- checks that it is allowed to publish,
- encrypts it, and pushes it to GitHub.

You should see `Connected @... It can publish.` after each one.

### 3.8 Publish the app

1. In the left menu, click **Publish** (or switch **App Mode** from Development to **Live**).
2. Meta lists anything missing. Usually that's a **Privacy Policy URL** (use the App Store privacy policy link of any of your apps) and an **app category**. Fill those in under **App settings** → **Basic**, then click **Publish**.

If Meta asks for **App Review** or **Business Verification** at this step, stop. Instagram posting works without publishing the app; just confirm in Part 4 that your first post is visible from an account that isn't yours.

---

## Part 4: Check that it works

1. On GitHub, open **Actions** → **Post to Instagram** → **Run workflow**.
2. Set **command** to `status` and click **Run workflow**.
3. Open the run and click the **post** job. You should see `connected as @...` for all 4 accounts, plus each one's next post.

That's it. From now on:

- Posts go out on their own.
- [SCHEDULE.md](SCHEDULE.md) on GitHub always shows the upcoming calendar.
- GitHub emails you if a run fails.

**After the first post:** look at it on Instagram from a phone that isn't logged in to that account. Check that it's visible and that every slide shows uncropped. The script also checks this itself (see "full-size check" in the run log).

---

## Part 5 (optional): Also post to Facebook Pages


### 5.1 Create one Page per app

1. Go to https://www.facebook.com/pages/create.
2. **Page name:** include the app's folder name so the script matches it automatically, for example `Cents: Finance Tracker`, `Lckdin`, `Pico Puzzles`, `Trivial`.
3. **Category:** type `App Page`.
4. Click **Create Page**, add the app icon as the profile picture, and finish the steps.
5. Repeat for the other apps.

Don't turn on **Automatically share to Facebook** in Instagram's or Accounts Center's settings. The script already posts to Facebook, so that setting would create duplicates.

### 5.2 Give the app Page permissions

1. In the Meta dashboard, open your app, then **Use cases** → **Add use case**.
2. Pick **Manage everything on your Page** and click **Add**.
3. If Meta doesn't allow adding it to this app, create a second app with only that use case (same steps as 3.2) and use that app in 5.3 and 5.4.
4. Back on **Use cases**, click **Customize** next to **Manage everything on your Page**. In its **Permissions** list, click **Add** next to each of these that isn't added yet:
   - `pages_show_list`
   - `pages_manage_posts`
   - `pages_read_engagement`

Graph API Explorer (step 5.4) only offers permissions that the app's use cases include. If you only see things like `pages_show_list`, `business_management` and `instagram_manage_comments` there, this step isn't done yet for the app you picked.

### 5.3 Note the App ID and secret

1. In the app, go to **App settings** → **Basic**.
2. Copy the **App ID**.
3. Click **Show** next to **App secret** and copy it.

### 5.4 Get a token and save the Pages

1. Open https://developers.facebook.com/tools/explorer.
2. On the right, set **Meta App** to your app.
3. Set **User or Page** to **Get User Access Token**.
4. Under **Permissions**, add `pages_show_list`, `pages_manage_posts` and `pages_read_engagement`. All three are required. If any is missing from the list, go back to step 5.2 (point 4), and check that **Meta App** is the app you added the Page use case to.
5. Click **Generate Access Token**. In the Facebook popup, select **all 4 Pages**, then continue and allow.
6. Copy the token from the **Access Token** box.
7. In VS Code, run:

   ```powershell
   python automation/poster.py add-facebook
   ```

8. Paste the App ID, the App secret and the token when asked.
9. For each app, press **Enter** to accept the Page it guessed, or type the right number.

It converts these into Page tokens that never expire, encrypts them, and pushes them.

### 5.5 Publish the app (required for Facebook)

Do step 3.8 if you haven't already. While a Meta app is in Development mode, Facebook hides the posts it makes from everyone except you.

From then on, every Instagram post also goes to that app's Facebook Page, with the same images and caption.

---

## Day-to-day

You don't have to do anything. Optional controls:

| To...                             | Do this                                                                                                                                                                                                    |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| See what's coming                 | Open [SCHEDULE.md](SCHEDULE.md) on GitHub.                                                                                                                                                                 |
| Post the next one right now       | **Actions** → **Post to Instagram** → **Run workflow**. Set command `post-now` and app `Cents` (add a number to pick a specific post).                                                                     |
| Retry a failed Facebook post      | **Run workflow** with command `retry-facebook`, the app, and the post number.                                                                                                                              |
| Pause an app                      | In `automation/config.json`, set that app's `"enabled"` to `false`, then commit and push.                                                                                                                  |
| Change a posting time             | Edit `"time"` in `automation/config.json`. Apps that post on the same day must be at least an hour apart. Then add the new time to the cron-job.org job ([ON-TIME-POSTING.md](ON-TIME-POSTING.md)), or it will only go out whenever GitHub's backup timer runs. |
| Add more posts                    | Add a folder with the next number (for example `27-P14-...`) with numbered images and `caption.txt`, then commit and push. Run `python automation/poster.py check` first to catch problems.                |
| Mark something you posted by hand | Add its number to that app's `already-posted.txt` and push. The script also notices on its own if a caption is already on the account.                                                                     |
| Stop everything                   | **Actions** → **Post to Instagram** → **⋯** → **Disable workflow**.                                                                                                                                        |

Things the API can't do, so you still do them by hand:

- pinning posts to the top of a profile,
- setting the link in bio.

**Tokens:** Instagram tokens last 60 days. The workflow renews them every week on its own. If you ever see `could not renew the Instagram token` in an email from GitHub, redo steps 3.6 and 3.7 for that account.
