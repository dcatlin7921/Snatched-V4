# How to Download Your Data from Snapchat

**Before you can use Snatched, you need your Snapchat data export.** This guide walks you through requesting and downloading everything — photos, videos, chats, locations, and more — directly from Snapchat.

The process is the same whether you start from the app or the website. Both routes end up at the same "My Data" page on `accounts.snapchat.com`.

---

## Why This Matters

Snapchat announced a **5 GB storage cap on free Memories** starting September 2026. After the deadline, any Memories exceeding 5 GB will be **permanently deleted — newest first**. That means your most recent photos and videos get erased before your oldest ones.

**You cannot recover deleted Memories.** Export now while you still can.

Paid alternatives exist ($1.99/mo for 100 GB, $3.99/mo for 250 GB, $15.99/mo for 5 TB), but exporting your data is free and gives you a permanent backup that Snapchat can never take away. If you cancel a paid plan while over 5 GB, you only get **48 hours** to resubscribe before over-limit Memories are deleted.

---

## What You'll Get

Your export arrives as one or more **ZIP files** containing:

| Content | What's Inside |
|---------|---------------|
| **Memories** | Every saved photo and video from your Memories (the `memories/` folder) |
| **Chat Media** | Photos and videos sent/received in DMs (the `chat_media/` folder) |
| **Shared Stories** | Story media you contributed to shared stories |
| **JSON Metadata** | 20+ metadata files with timestamps, GPS locations, friend lists, chat logs, and more |
| **HTML Files** | Browser-viewable pages with an `index.html` for navigating your data |

### What Snapchat Does NOT Include

There are some important things to know about what you'll receive:

- **No EXIF metadata on media files.** Snapchat strips all date/time and GPS data from exported photos and videos. Every file will show the *download date* in your gallery app — not when it was actually taken. The real dates and locations are only preserved in the JSON metadata files. **This is exactly why Snatched exists** — we reunite your media with its metadata.
- **Overlays are separate.** Filters, stickers, text, and drawings are exported as separate PNG files — they are NOT baked into your photos. Snatched automatically merges them back together.
- **Expired and deleted Snaps are gone.** Only content saved to Memories is exportable. Ephemeral Snaps that weren't saved cannot be recovered.
- **Chat media is limited.** The chat export includes text message logs and some media, but not every image/video ever sent in a conversation.

---

## Step-by-Step Guide

### Getting to "My Data"

**From the Snapchat App (iOS or Android):**

1. Open Snapchat and tap your **profile icon / Bitmoji** (top-left corner)
2. Tap the **gear icon** (top-right corner) to open Settings
3. Scroll down to the **Privacy Controls** section
4. Tap **"My Data"**
5. This opens `accounts.snapchat.com` in your mobile browser
6. Log in again if prompted (this is a security verification)

**From a Computer:**

1. Go to **accounts.snapchat.com** in any web browser
2. Log in with your Snapchat username and password (+ 2FA if enabled)
3. Click **"My Data"** from the menu

Both paths take you to the same page. We recommend using a **computer** for the actual download since the ZIP files can be several gigabytes.

> **Note:** If this is the first time you're accessing My Data from a new device, Snapchat may impose a **72-hour security hold** before processing your request. Plan ahead.

---

### Configuring Your Export

Once you're on the My Data page, you'll see toggles and checkboxes. **For the best results with Snatched, enable everything.**

#### Top Toggles (Critical)

These toggles appear at the top of the page. **All must be ON:**

| Toggle | What It Does | Required? |
|--------|-------------|-----------|
| **Export your Memories** | Includes your saved photos/videos + `memories_history.json` | **YES — Essential** |
| **Export JSON Files** | Includes all metadata files (timestamps, GPS, friends, chat logs) | **YES — Essential** |

Without "Export JSON Files," Snatched has no metadata to work with — your photos will have no dates or locations. Without "Export your Memories," you won't get your saved media.

> **Memories-Only Shortcut:** When you toggle "Export your Memories" ON, a blue **"Request Only Memories"** button appears. Do NOT use this shortcut — it skips all other data categories. You want the full export for best results with Snatched.

#### Data Categories (Select ALL)

Below the top toggles, you'll see data categories with checkboxes. The exact number and grouping may vary slightly over time, but as of 2026 they include:

| # | Category | What It Includes | Why Snatched Needs It |
|---|----------|-----------------|----------------------|
| 1 | **User Information** | Login history, profile, friends list, Bitmoji, connected apps | Friend name resolution |
| 2 | **Chat History** | Snap history, chat logs, talk history, communities | Chat rendering + timestamps |
| 3 | **Spotlight** | Shared stories, spotlight replies, story history | Story media matching |
| 4 | **Shopping** | Purchase history, subscriptions, orders, payments | Complete backup |
| 5 | **Support History** | Support tickets, surveys, reported content | Complete backup |
| 6 | **Ranking And Location** | Statistics, **GPS location history**, ads, Snap Map places | **GPS enrichment — critical** |
| 7 | **Other Media** | Custom sounds, custom stickers | Media matching |
| 8 | **Other** | Search history, lenses, selfie & cameos, Snap AI, countdowns | Complete backup |
| 9 | **My AI** | My AI conversations, AI features | Complete backup |
| 10 | **Export Shared Stories** | Shared story media files | Story media export |

**Categories 1, 2, 3, 6, and 10 are critical for Snatched.** The others don't hurt to include and ensure you have a complete backup of your entire Snapchat history.

#### Bottom Toggle (Important)

| Toggle | What It Does | Required? |
|--------|-------------|-----------|
| **Export Chat Media** | Includes actual photos/videos from DM conversations | **YES — if you want chat media** |

This gives you the `chat_media/` folder with photos and videos from your DM conversations.

---

### Choosing a Date Range

After selecting your categories and clicking **Next**, you'll see a date range selector:

| Option | What It Means |
|--------|--------------|
| **Toggle OFF (All Time)** | Everything from account creation to now — **recommended** |
| **Last Year** | Only the past 12 months |
| **Last Week** | Only the past 7 days |
| **Custom Range** | Pick specific start and end dates |

Snapchat's own wording: *"Choose the date range of data you'd like to receive or toggle this off if you want to receive all data."*

**We strongly recommend "All Time."** You're doing this to rescue your data before the storage cap hits. Get everything in one request. You can always filter later in Snatched.

---

### Submitting Your Request

1. Confirm or update the **email address** where you want to be notified
2. Click **"Submit"** at the bottom of the page
3. Snapchat begins preparing your export

**How long does it take?**
- Small accounts (metadata only): 15–30 minutes
- Medium accounts (under 5 GB): a few hours to 24 hours
- Large accounts (5+ GB): 24–48 hours, sometimes longer
- Snapchat officially aims to deliver within **7 days** for large exports

You'll receive an **email notification** when your data is ready. The email subject will be something like "Your Snapchat Data is Ready for Download."

---

### Downloading Your Export

You don't need the email to download — you can check the My Data page directly:

1. Go back to `accounts.snapchat.com` > **My Data**
   - Or: open the Snapchat app > Settings > Privacy Controls > My Data
2. Look for **"Data available for download"** or click **"See exports"** at the top
3. Click **"Download"** next to your export

**Important timing:**
- Your download links expire after approximately **72 hours** (3 days) from when the export is generated
- The CDN links inside `memories_history.json` (used to download your actual media) also expire at 72 hours
- **Download immediately** when you get the notification — don't wait
- Snapchat limits how many export requests you can make per day, so you don't want to have to re-request

**What you'll download:**
- One or more **ZIP files** (large exports are automatically split across multiple ZIPs, e.g. `mydata~1234567890.zip`, `mydata~1234567890-2.zip`, `mydata~1234567890-3.zip`)
- Total size depends on your Memories — can range from a few hundred MB to 10+ GB
- Make sure you have roughly **2x the ZIP size** in free disk space for extracting

---

### Saving Your Files

1. Save the ZIP file(s) to your computer
2. **Do NOT unzip them** — Snatched accepts the raw ZIP files directly
3. Keep the original ZIPs as a backup even after processing

If you downloaded on your phone:
- **iPhone:** Check the Files app > Downloads folder
- **Android:** Check your Downloads folder or Files app
- We recommend transferring the ZIP(s) to a computer for uploading to Snatched — phone uploads over cellular can be unreliable for multi-gigabyte files

---

## Why Not Just Export from the Snapchat App Directly?

Snapchat does let you save Memories to your camera roll directly from the app — but there are serious limitations:

- **Capped at 100 items per batch.** If you have thousands of Memories, you'll be tapping and waiting for hours.
- **Still no EXIF metadata.** Files saved to camera roll have the save date, not the original capture date. No GPS data.
- **No chat history, location data, or friend metadata.** The in-app save only exports the media, not the rich metadata.
- **No overlays.** Filters and stickers are not applied to saved files.

The **My Data web export** gives you everything in one shot — media, metadata, chat logs, GPS history, friend lists. That's what Snatched is built to process.

---

## Using Your Export with Snatched

Once you have your ZIP file(s):

1. Go to **Snatched** and log in
2. Click **"Upload"** on your dashboard
3. Drag and drop your ZIP file (or click to browse)
4. Snatched automatically detects what's inside and begins processing
5. Watch the pipeline run: **Ingest -> Match -> Enrich -> Export**
6. Download your organized archive with all metadata restored

**What Snatched does with your export:**
- Parses all JSON metadata files to extract original timestamps, GPS coordinates, and friend names
- Matches each media file to its metadata using a 6-strategy cascade (up to 100% confidence)
- Cross-references GPS location history to enrich files that lack coordinates
- Burns overlay PNGs (filters, stickers, text) back onto your photos
- Embeds proper EXIF tags so your photos show the right date and location in any gallery app
- Renders chat conversations as high-resolution PNG images
- Packages everything into a clean, organized download

Snatched accepts ZIP files up to **5 GB** per upload. If your Snapchat export was split into multiple ZIPs, upload them as separate jobs.

---

## Troubleshooting

**"I never got the email"**
- Check your spam/junk folder
- You don't need the email — go directly to `accounts.snapchat.com` > My Data > See exports to download

**"The download link expired"**
- Request a new export (same steps as above)
- Download immediately next time — links expire after 72 hours
- This is also why we recommend requesting ALL data in one export rather than multiple small ones

**"My export is missing Memories / no photos or videos"**
- Make sure **"Export your Memories"** was toggled ON at the top of the page
- If you only see JSON files and chat media but no `memories/` folder, you exported "My Data" without the Memories toggle

**"My export has no JSON files / Snatched says no metadata found"**
- Make sure **"Export JSON Files"** was toggled ON
- Without this, you only get raw media with no metadata — Snatched needs the JSON files to restore your dates and locations

**"I hit the daily request limit"**
- Snapchat limits export requests per day
- Wait 24 hours and try again
- This is why we recommend selecting ALL categories and ALL date ranges in one request

**"Snapchat says try again in 72 hours"**
- This happens when requesting data from a new or unrecognized device
- It's a security measure — wait the 72 hours and try again from the same device

**"The ZIP is huge and my upload is slow"**
- Large exports (5+ GB) take time to upload
- Use a wired connection if possible
- Snatched shows upload progress so you can monitor it
- Consider uploading from a computer rather than a phone

**"My photos all show today's date in my gallery"**
- This is exactly the problem Snatched solves
- Snapchat strips original dates from exported files — the dates only exist in the JSON metadata
- Upload to Snatched and it will embed the correct dates back into your photos via EXIF

---

## Quick Reference Checklist

Before you hit Submit, make sure:

- [ ] **Export your Memories** — ON
- [ ] **Export JSON Files** — ON
- [ ] **All data categories** — ON (every single one)
- [ ] **Export Chat Media** — ON
- [ ] **Export Shared Stories** — ON
- [ ] **Date range** — set to **All Time** (toggle OFF)
- [ ] **Email address** — correct and accessible

**Then:** Submit -> Wait for email -> Download immediately -> Upload to Snatched

---

## The September 2026 Deadline

Snapchat's free storage cap goes into effect **September 2026**:

- Free accounts are limited to **5 GB** of Memories storage
- A 12-month grace period started September 2025
- After the deadline, excess Memories are **permanently deleted**
- Snapchat deletes your **newest Memories first** (your oldest ones survive under the cap)
- There is **no recovery** for deleted Memories
- Canceling a paid plan while over 5 GB gives you only **48 hours** before deletion begins

**Don't wait.** Export your data today, upload it to Snatched, and keep your memories forever.

---

*Snatched is not affiliated with Snap Inc. This guide is based on Snapchat's official data export process as of 2026. Source: [Snapchat Help — How do I download my data?](https://help.snapchat.com/hc/en-us/articles/7012305371156)*
