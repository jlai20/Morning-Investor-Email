# Morning Email

Daily briefing from fund manager insights, newsletters, and curated Twitter/X accounts — summarised by AI and sent to your inbox at 6am AEST.

**Cost: $0/month.** Uses GitHub Actions (free) and Google Gemini API (free tier).

---

## Setup — 3 steps

### Step 1 — Get your free Gemini API key (2 minutes)

1. Go to **aistudio.google.com/apikey**
2. Sign in with your Google account (the same one as your Gmail)
3. Click **Create API key** → Copy it

That's it. No credit card. Free forever for this usage level.

---

### Step 2 — Create a GitHub repository (5 minutes)

1. Go to **github.com** and create a free account if you don't have one
2. Click **+** (top right) → **New repository**
3. Name it `morning-emails`, set to **Private**, click **Create repository**
4. Upload all files from this folder: drag and drop them onto the GitHub page

---

### Step 3 — Add your secrets (3 minutes)

In your GitHub repo go to: **Settings → Secrets and variables → Actions → New repository secret**

Add these 4 secrets one at a time:

| Secret name | Value |
|---|---|
| `GMAIL_USER` | `jlai5212@gmail.com` |
| `GMAIL_APP_PW` | Your Gmail app password (16 characters) |
| `GEMINI_API_KEY` | The key you copied in Step 1 |
| `RECIPIENT_EMAIL` | `jlai5212@gmail.com` |

---

## Test it

Go to the **Actions** tab in your repo → click **Morning Email** → click **Run workflow** → **Run workflow**.

Check your inbox in 2–3 minutes.

After that it runs automatically every day at 6am AEST.

---

## Adding or removing sources

Edit `sources.yaml`. No other file needs to change.

To add a newsletter or website:
```yaml
- name: "Display Name"
  type: scrape
  url: "https://..."
```

To add a Twitter/X account:
```yaml
- name: "Person Name"
  type: nitter
  handle: "TwitterHandle"  # without the @
```
