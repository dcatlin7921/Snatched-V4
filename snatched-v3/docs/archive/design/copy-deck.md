# Snatched v3 — Complete User-Facing Copy Deck

**Last Updated**: 2026-02-24

## Brand Voice

**Tone**: Clear, warm, action-oriented. Think Stripe, Linear, Vercel quality.
- No jargon. If we use technical terms, explain them.
- Empowering, not scary. Users are rescuing their memories—celebrate that.
- Short sentences. Scannable lists. Calls to action are clear buttons, not buried in prose.
- Active voice. "We process" not "processing occurs."

---

## 1. LANDING PAGE

### Hero Section

**Main Headline:**
```
Rescue Your Snapchat Memories
```

**Subheadline:**
```
Upload your Snapchat export. We'll organize your photos, chats, and stories—with dates, locations, and friend names automatically restored.
```

**Why it works:**
- Leads with the emotional benefit (rescue) not the feature (processing).
- Specific: mentions the three main outputs users care about.
- Concrete: "dates, locations, friend names" are tangible, not abstract.

### Feature Bullet Points (Rewritten)

**Section Header:**
```
What You Get
```

**Features:**
1. **Smart Matching**
   ```
   Six different strategies find the right metadata for each photo—99% accuracy from Snapchat's organized exports.
   ```

2. **Location & Friend Names**
   ```
   GPS data is recovered and embedded. Friends you snapchatted with are named, not numbered.
   ```

3. **Organized Folders**
   ```
   Everything sorted by date and type. Import straight into Immich, Google Photos, or your own backup.
   ```

4. **Metadata Everywhere**
   ```
   Dates, locations, and creation info embedded into files. Portable to any photo app forever.
   ```

**Why they work:**
- Each opens with the user outcome (what they get), not the technical feature.
- Specific: "six different strategies," "99% accuracy," "import straight into Immich."
- No jargon: no "cascade matching" or "EXIF embedding"—just "metadata embedded into files."

### How It Works Section

**Section Header:**
```
The 4 Phases
```

**Steps (scannable):**

1. **Export**
   ```
   Go to Snapchat Settings → Download My Data.
   ```

2. **Upload**
   ```
   Drop the ZIP here. No account needed, no data stored after processing.
   ```

3. **Processing**
   ```
   ~10–30 minutes. We match, enrich, and organize your files in 4 phases. Live progress streamed to you.
   ```

4. **Download**
   ```
   Get a single ZIP or individual folders. Import to any photo app.
   ```

**Why it works:**
- Numbered steps, one sentence each. Clear. Scannable.
- Addresses the unspoken worry: "no data stored after processing" = privacy-respecting.
- Sets expectation: "~10–30 minutes" prevents users from leaving the tab.

### Call-to-Action Buttons

**Primary CTA (on hero):**
```
Start Processing
```

**Secondary CTA (in section):**
```
View All Features
```

**In navigation:**
```
Upload Export    |    View Jobs
```

**Why:**
- "Start Processing" is more active than "Upload" alone.
- "View All Features" invites without commitment.
- Both are clear about what happens next.

---

## 2. UPLOAD PAGE

### Page Title & Description

**Title:**
```
Upload Your Snapchat Export
```

**Description:**
```
Max size: 5 GB. Accepts .zip files only. Processing takes 10–30 minutes depending on file size.
```

**Why:**
- Concrete limit (5 GB) and format (.zip).
- Sets expectation for wait time.

### Drag-Drop Zone

**Idle State:**
```
Drag and drop your ZIP file here
or choose a file
```

**On Hover:**
```
Drop your file to start
```

**After Drop (before upload):**
```
Ready to process: filename.zip (2.3 GB)
```

**Why:**
- Idle: friendly, not demanding.
- Hover: confirmatory, shows the zone is active.
- After drop: user sees file name + size for confidence.

### Processing Options Section

**Legend:**
```
Processing Options
```

**Option 1: Burn Overlays**

```
☑ Add date & time text to photos
```

**Helper text (on hover or below):**
```
Overlays the capture date and time as text on each photo. Useful for printing or sharing. Tip: you can always add overlays later in Photoshop if you change your mind.
```

**Why:**
- "Add date & time text" is concrete, not "burn overlays."
- Helper explains why you'd want it (printing, sharing).
- Removes fear: says you can undo this with Photoshop.

---

**Option 2: Dark Mode Chat PNGs**

```
☐ Export chats in dark mode
```

**Helper text:**
```
Snapchat chat conversations are exported as high-res images. This option renders them with a dark background. Light mode is the default. Both versions are readable for printing or archiving.
```

**Why:**
- Concrete: "export chats as high-res images"—explains what the feature is.
- Practical: both light and dark are readable, so it's a style choice, not a functional one.
- Addresses use case: "for printing or archiving."

---

**Option 3: Embed EXIF Metadata**

```
☑ Embed dates, locations, and camera info in files
```

**Helper text:**
```
Photos get EXIF metadata so tools like Immich, Google Photos, and Lightroom recognize the date and location. Your memories will import with the right timestamp and map pin. Required for location-aware photo libraries.
```

**Why:**
- "Embed dates, locations, and camera info" is clear.
- Named specific tools: Immich, Google Photos, Lightroom.
- Explains consequence: "right timestamp and map pin."
- Notes it's "required for location-aware photo libraries" so users understand the importance.

---

**Option 4: XMP Sidecar Files** *(if visible—currently hidden)*

```
☐ Save metadata as separate XMP files (advanced)
```

**Helper text:**
```
Stores photo metadata in separate .xmp sidecar files instead of embedding. Use this if you need to edit metadata later, or if importing to Lightroom. Leave off unless you know you need it.
```

**Why:**
- Leads with the outcome: "save metadata separately."
- Targets specific use case: Lightroom editing.
- "Leave off unless you know you need it" = defaults to the simple path.

---

**Option 5: GPS Window Slider** *(if visible—currently hidden)*

```
GPS Time Window:  [===|========] 5 minutes
```

**Helper text:**
```
How far apart can a photo and a Snap location be in time? Wider windows match more memories but may be less accurate. The default 5 minutes is a safe balance.
```

**Why:**
- Clear label: "GPS Time Window."
- Visual feedback: the slider shows the current value.
- Explains the tradeoff: wider = more matches, less accuracy.
- Defends the default: "safe balance."

---

### Submit Button

```
Process Export
```

**Why:**
- "Process Export" is active and clear.
- Not just "Upload"—emphasizes that work will begin.

### Upload Progress

**While uploading:**
```
Uploading and validating your ZIP file...
[████████░░░░░░░░░░] 45%
```

**After successful upload:**
```
✓ File uploaded successfully.
Your job has started. Redirecting to progress page...
```

**Why:**
- Shows percentage to build confidence.
- Checkmark on success.
- "Redirecting" manages expectation.

### Error Messages

**Wrong file type:**
```
Sorry, we only accept .zip files. Please try again.
```

**File too large:**
```
Your file is 6.2 GB, but the maximum is 5 GB. Please split the export or try a smaller selection.
```

**Quota exceeded:**
```
You've reached your storage limit (10 GB / month). Delete an old job to free space, or wait until next month. Need more? [Upgrade Plan]
```

**Invalid or corrupted ZIP:**
```
This ZIP doesn't look like a Snapchat export. Check that you exported from Settings → Download My Data. If it's still not working, email support@snatched.app.
```

**Why:**
- Each explains what went wrong and suggests a fix.
- Specific numbers (file size, quota) build trust.
- Links to next steps (delete, upgrade, support).
- Empathetic: "Check that you exported..."

---

## 3. DASHBOARD

### Page Title & Description

**Title:**
```
Dashboard
```

**Description:**
```
Manage your processing jobs.
```

### Section: Active Jobs

**Section Header:**
```
Active Jobs
```

**If jobs exist:**
- Show job cards (see Job Card format below).

**If empty:**
```
No active jobs.
Ready to process? [Upload a New Export]
```

**Why:**
- Empty state is actionable.
- Button suggests next step without guilt.

### Section: Job History

**Section Header:**
```
Job History
```

**If jobs exist:**
- Show job cards in reverse chronological order.

**If empty:**
```
You haven't processed any exports yet.
Your downloads will appear here once you upload a Snapchat export. [Get Started]
```

**Why:**
- Educational: explains what will show up.
- Actionable: button links to upload.

### Job Card Format

Each card displays:

**Card Layout:**
```
┌─────────────────────────────────┐
│ Job #1234 | [●] RUNNING         │
│ Started: Feb 24, 2025, 2:15 PM  │
│ File: snapchat_export.zip        │
│ Size: 2.3 GB                      │
│ ────────────────────────────────  │
│ Progress: Enriching (Phase 3)     │
│ [████████░░░░░░░░░░] 65%          │
│ Est. complete: 2:45 PM            │
│ ────────────────────────────────  │
│ [⏯ Pause] [↺ Reprocess] [View↗]   │
└─────────────────────────────────┘
```

**Status Badge Labels:**

- **Pending** (light gray): `⏳ Waiting to process...`
- **Running** (blue/yellow): `● Running — Phase 2: Match`
- **Completed** (green): `✓ Complete — Ready to download`
- **Failed** (red): `✗ Failed — Click for details`
- **Cancelled** (gray): `⊝ Cancelled`

**Why:**
- Icon + word + color. No confusion.
- Shows current phase, not just "running."
- Progress bar + percentage.
- Estimated completion time sets expectation.

### Action Buttons on Job Card

**For running jobs:**
```
[View Progress] [Cancel Job]
```

**For completed jobs:**
```
[View Results] [Download] [Reprocess]
```

**For failed jobs:**
```
[View Error] [Retry] [Delete]
```

**Why:**
- Action verbs.
- "View Progress" is clearer than "Monitor."
- "Retry" gives users agency after failure.

### Cancel Confirmation Dialog

**Dialog Title:**
```
Cancel This Job?
```

**Dialog Message:**
```
Cancelling will stop processing. You won't be able to download results.

This action cannot be undone.
```

**Buttons:**
```
[Cancel Processing]  [Keep Processing]
```

**Why:**
- Emphasizes the consequence: "stop processing" and "won't be able to download."
- "Cannot be undone" sets finality.
- Button order: destructive action first, safety second.

---

## 4. JOB PROGRESS PAGE

### Page Title

```
Job #1234 — Processing
```

### Phase Names & Descriptions

Displayed in a 2×2 grid:

**Phase 1: Ingest**
```
Phase 1: Ingest
Reading your Snapchat data files and scanning media.
Status: ✓ Complete
```

**Phase 2: Match**
```
Phase 2: Match
Finding the right metadata for each photo using 6 matching strategies.
Status: ● Running
```

**Phase 3: Enrich**
```
Phase 3: Enrich
Adding GPS locations, friend names, and organizing by date.
Status: ⏳ Waiting
```

**Phase 4: Export**
```
Phase 4: Export
Writing your organized files and generating chat PNGs.
Status: ⏳ Waiting
```

**Why:**
- Each phase name is preceded by a number.
- Description is one sentence in plain English.
- Status is clearly visible with icon.

### Overall Progress

**Display:**
```
Overall Progress
[████████████░░░░░░░░░░] 63%
Approximately 8 minutes remaining
```

**Why:**
- Shows both absolute (63%) and relative (8 minutes) progress.
- Helps user decide: "Can I leave the tab now?"

### Log Output

**Label:**
```
Live Processing Log
```

**Display:**
```
[timestamp] INFO: Parsed 2,151 breadcrumb locations
[timestamp] INFO: Matched 1,847 photos using exact_media_id strategy
[timestamp] INFO: Starting GPS enrichment...
[timestamp] WARNING: 42 photos lack GPS data (no Snap locations)
```

**Why:**
- Monospace font, dark background.
- Timestamps + log level (INFO/WARNING/ERROR).
- Last entry is always visible (auto-scroll).

### Completion Message

**When job completes:**
```
✓ Complete!

Your job processed 2.3 GB in 18 minutes.
Ready to download 8,472 files.

[View Results] [Start New Export]
```

**Why:**
- Celebratory (✓) but brief.
- Specific stats: size, time, file count.
- Clear next steps.

---

## 5. RESULTS PAGE

### Page Title & Summary

**Title:**
```
Results — Job #1234
```

**Completion timestamp (gray, below title):**
```
Completed on Feb 24, 2025 at 2:35 PM
```

### Tab Navigation

```
[Summary] [Matches] [Assets]
```

---

### TAB 1: SUMMARY

**Section: Key Stats**

```
Key Stats

[icon] Total Memories      [icon] Matched         [icon] Match Rate      [icon] GPS Coverage
    2,847                      2,754                    96.7%                   84.2%
```

**Stat Card Labels:**
- **Total Memories**: "Total Memories" (all photo/video files)
- **Matched**: "Matched" (have metadata attached)
- **Match Rate**: "Match Rate" (as %)
- **GPS Coverage**: "GPS Coverage" (photos with location data, as %)

**Why:**
- Simple counts.
- "Match Rate" is clearer than "Matching Success."
- GPS coverage sets expectation for location features.

---

**Section: Breakdown by Lane**

**Table Header:**
```
Data Lane      Photos    Videos    Matched    GPS
Stories           412       68        468       382
Memories        1,845      287      2,089     1,702
Chats             520        0        197         0
Totals          2,777      355      2,754     2,084
```

**Column Descriptions (on hover):**
- **Lane**: Type of Snapchat data (Stories, Memories, Chats, Spotlight, etc.)
- **Photos**: Number of photo files in this lane.
- **Videos**: Number of video files.
- **Matched**: How many have metadata attached.
- **GPS**: How many have location data.

**Why:**
- Shows what was exported.
- Reveals the story: "All stories matched, but no chats have GPS."
- Helps user understand where the 3% unmatched came from.

---

**Section: Processing Time**

**Table:**
```
Phase          Duration       % of Total
Ingest         1 min 24 sec       7.8%
Match          7 min 33 sec      42.0%
Enrich         4 min 18 sec      23.9%
Export         4 min 45 sec      26.4%
Total          18 min             100%
```

**Why:**
- Shows where time went.
- Helps debug: if Export is always slow, that's useful feedback.
- Expectation-setting for next upload.

---

**CTA:**
```
[Download Your Results]
```

---

### TAB 2: MATCHES

**Header:**
```
Matches
```

**Description (if no matches):**
```
No matches found in this export.

This is rare. It usually means the Snapchat export didn't include metadata (dates, story info, etc.). Check that you exported from Settings → Download My Data.

[Contact Support]
```

**If matches exist, show paginated table:**

```
Asset ID      Type     Date/Time            Confidence    Strategy Used
dGH3k2j...    Photo    2024-08-15 3:45 PM   100%          exact_media_id
xL9Qr4m...    Video    2024-08-15 4:02 PM    90%          story_id
9Wk1pL6...    Photo    2024-08-14 11:22 AM   80%          timestamp_type
```

**Column Descriptions:**
- **Asset ID**: First 8 chars of file hash (unique identifier).
- **Type**: Photo, video, or chat.
- **Date/Time**: When the memory was captured (if matched).
- **Confidence**: 100% = exact match, 30–90% = probable match.
- **Strategy**: Which matching rule found the metadata.

**Why:**
- "Confidence" + "Strategy" are transparent about how certain we are.
- Users can spot patterns: e.g., "all videos matched via story_id" suggests that lane is solid.
- ID + timestamp is useful for debugging if user suspects an error.

---

### TAB 3: ASSETS

**Header:**
```
Exported Assets
```

**Description (if no assets):**
```
No assets exported for this job.

Assets are the files you'll download: photos, videos, chat PNGs, and metadata. If this number is zero, check the upload log for errors.

[Contact Support]
```

**If assets exist, show paginated table:**

```
Filename                    Size       Type       EXIF Status       Format
IMG_2024-08-15_154523.jpg   3.2 MB     Photo      ✓ Embedded        JPEG
VID_2024-08-15_160102.mp4   45.1 MB    Video      ✓ Embedded        MP4
chat_alex_20240815.png      2.8 MB     Chat PNG   —                 PNG (no metadata)
```

**Column Descriptions:**
- **Filename**: How the file is named in the download ZIP (organized by date, type).
- **Size**: File size in human-readable format.
- **Type**: Photo, video, or chat conversation.
- **EXIF Status**: ✓ (embedded), — (N/A for chats), ✗ (failed).
- **Format**: JPEG, MP4, PNG, etc.

**Why:**
- Users can spot large files before downloading.
- "EXIF Status" is transparent: "✓ Embedded" means Immich will recognize the date.
- Chat PNGs note "no metadata" because images don't need EXIF.

---

## 6. DOWNLOAD PAGE

### Page Title

```
Download Results — Job #1234
```

### Section: Download All

**Card Title:**
```
Download Everything
```

**Main CTA:**
```
Download All as ZIP
```

**Helper Text (below button):**
```
8,472 files packaged into a single download (2.3 GB compressed). Once downloaded, unzip to access your photos, videos, chats, and metadata.

Contains: organized folders, chat transcripts, metadata sidecar files (if enabled), and a processing report.
```

**Size estimate (small gray text):**
```
Size: ~2.3 GB (compressed)
Estimated download time: 12–45 minutes on a 10 Mbps connection
```

**Why:**
- Clear what's in the download.
- Size + time estimate manages expectation.
- Explains folder structure so users know what to expect when unzipping.

---

### Section: Download Individual Files

**Header:**
```
Browse & Download
```

**File Tree Structure (example):**
```
📁 memories/
   📁 2024-08-15/
      📄 IMG_20240815_154523.jpg  [Download]
      📄 IMG_20240815_160102.mp4  [Download]
   📁 2024-08-14/
      📄 IMG_20240814_112245.jpg  [Download]

📁 stories/
   📁 2024-08-15/
      📄 story_alex.mp4           [Download]

📁 chats/
   📄 conversation_alex.png       [Download]
   📄 conversation_alex.txt       [Download]

📁 metadata/
   📄 processing-report.json      [Download]
   📄 matches.csv                 [Download]
```

**Folder Labels (expandable with click):**
```
Memories: 2,754 photos & videos organized by capture date
Stories: 480 snapchat stories
Chats: 197 conversations as PNG images + text transcripts
Metadata: Processing report, match details, pipeline stats
```

**File-Level Actions:**
- **Download**: Downloads single file.
- **Copy path**: Copies full path to clipboard (for scripting).
- **Info**: Shows file size, EXIF data (if any), export timestamp.

**Why:**
- Folder structure is immediately clear.
- Users can cherry-pick files if download all is too large.
- "Copy path" is useful for advanced users who want to script cleanup/import.

---

### Navigation

**Below download section:**
```
[View Summary] [Process Another Export]
```

**Why:**
- Quick path back to review stats.
- Button to upload again (common use case: "I forgot some memories").

---

## 7. SETTINGS / ACCOUNT PAGE (NEW)

### Page Title

```
Settings
```

### Section 1: Processing Preferences

**Header:**
```
Default Processing Options
```

**Setting: Default Burn Overlays**
```
☑ Add date/time text to memories by default
```

**Helper:**
```
Every new job will use this setting unless you change it on the upload page.
```

**Setting: Default Dark Mode Chats**
```
☐ Export chats in dark mode by default
```

**Helper:**
```
Applies to all future jobs. You can still change this per upload.
```

**Setting: Default EXIF Embedding**
```
☑ Embed metadata in photos by default
```

**Helper:**
```
Highly recommended for photo library imports (Immich, Google Photos, Lightroom).
```

**Why:**
- Users save time on repeat uploads.
- Helper text explains why (Immich, etc.).
- "Per upload override" gives flexibility.

---

### Section 2: Storage & Quota

**Header:**
```
Storage
```

**Display:**
```
Your Storage: 6.8 GB / 10 GB
[████████░░░░░░░░░░░░░░] 68% used

This month: 2 jobs processed (3.2 GB)
Quota resets: March 1, 2025
```

**Action:**
```
[View Retention Policy]
```

**Helper:**
```
Downloads older than 30 days are deleted to free space. Backups to your own cloud storage are not counted toward this limit.
```

**Why:**
- Visual progress bar (68%).
- Shows what's consumed this month.
- Explains retention so users don't panic.

---

### Section 3: Account

**Header:**
```
Account
```

**Display:**
```
Username:              davemint
Email:                 dave@example.com
Account created:       Jan 15, 2025
Plan:                  Free Tier (10 GB/month, 5 GB max upload)
```

**Tier Options (if available):**
```
Plan      Storage    Max Upload   Price
Free      10 GB      5 GB         Included   [Current]
Plus      50 GB      25 GB        $4.99/mo   [Upgrade]
Pro       500 GB     100 GB       $14.99/mo  [Upgrade]
```

**Account Actions:**
```
[Change Password]  [Manage Email]  [Delete Account]
```

**Danger Zone:**
```
⚠️ Danger Zone

[Delete My Account]
This will delete your account and all stored data. This cannot be undone.
```

**Why:**
- Clear tier breakdown.
- Danger Zone = red, separate, intentional.
- "Cannot be undone" emphasizes finality.

---

## 8. GLOBAL / SHARED COPY

### Navigation Bar

**Logo / Home:**
```
Snatched v3
```

**Nav Items:**
```
Dashboard     |     Upload     |     [username] ▼
```

**Dropdown Menu (under username):**
```
Settings
Account
Logout
```

**Why:**
- Dashboard, Upload = main actions.
- Username as menu trigger is clear.

---

### Footer

**Text:**
```
Snatched v3 — Snapchat Export Processor
© 2025. Privacy Policy | Terms | Support | GitHub
```

**Why:**
- Minimal, informative.
- Links to legal + support.

---

### Toast / Notification Messages

**Job Started:**
```
✓ Upload complete! Your job (#1234) is now processing.
```

**Job Completed:**
```
✓ Done! Job #1234 is ready to download.
```

**Job Failed:**
```
✗ Error: Job #1234 failed during Phase 2. [View Details]
```

**Upload Error:**
```
✗ Invalid ZIP file. Make sure you exported from Snapchat Settings → Download My Data.
```

**Quota Warning:**
```
⚠️ Your storage is 90% full. [Free space or upgrade]
```

**Connection Lost:**
```
⚠️ Connection interrupted. Reconnecting...
```

**Why:**
- Icon + status code (✓ or ✗ or ⚠️) is immediate.
- Link to relevant action (Details, Free space, etc.).
- Copy is concise for small toast areas.

---

### Generic Error Page

**Title:**
```
Something Went Wrong
```

**Message (varies by error):**

**500 Internal Error:**
```
Our servers hit a snag. This is on us, not you.

Please try refreshing the page, or [email support](mailto:support@snatched.app) and we'll look into it.

Your job ID: #1234 (include this in your email so we can help faster)
```

**404 Not Found:**
```
This job doesn't exist or has been deleted.

[Back to Dashboard]
```

**403 Forbidden:**
```
You don't have permission to access this job.

[Back to Dashboard]
```

**Network Timeout:**
```
The request took too long. Your internet connection might be slow, or our servers are overloaded.

Please try again in a moment, or [contact support](mailto:support@snatched.app).
```

**Why:**
- Each error explains what happened in plain English.
- Suggests next steps (refresh, contact support, try again).
- Job ID is helpful for support.

---

### Confirmation Dialogs

**Cancel Job Confirmation (already in section 3):**
```
Cancel This Job?
Cancelling will stop processing. You won't be able to download results.
This action cannot be undone.

[Cancel Processing]  [Keep Processing]
```

**Delete Account Confirmation:**
```
Delete Your Account?
This will permanently delete your account and all stored data.

Type "delete" to confirm:
[_________________]

[Delete Permanently]  [Cancel]
```

**Why:**
- Asks user to type the action word (safety measure).
- Destructive button is red, cancel is gray.

---

## TECHNICAL NOTES FOR IMPLEMENTATION

### Placeholder Values
- Job numbers (e.g., #1234) = mock for documentation. API will return real IDs.
- File sizes, percentages, durations = placeholders. Use real data from API.
- Timestamps = use browser timezone.

### Accessibility Considerations
- All buttons have `role="button"` and text labels (no icon-only).
- Status badges use color + text (not color-only).
- Form inputs have associated `<label>` tags.
- Modals are marked with `role="dialog"` and have close buttons.
- Phase progress uses numeric % as well as visual bar.

### Responsive Breakpoints
- **Mobile** (<640px): Single-column layout, full-width buttons, collapsible sections.
- **Tablet** (640–1024px): Two-column stats grid, side-by-side tabs.
- **Desktop** (>1024px): Full 4-column grid, multi-pane layout.

### Color Usage
- **Blue** (#0066cc): Primary actions, running status, focus states.
- **Green** (#00cc00): Success, completion.
- **Yellow** (#ffcc00): Warning, pending state.
- **Red** (#cc0000): Error, critical actions.
- **Gray**: Neutral, disabled, cancelled.

### Animations
- Progress bars: smooth `width` transition over 0.5s.
- Status badges: instant text/color change on phase transition.
- Modals: fade in over 0.3s.
- Buttons: scale 0.98 on hover (subtle press effect).

---

## A/B TESTING OPPORTUNITIES

1. **Hero headline**: "Rescue Your Snapchat Memories" vs. "Organize & Backup Your Snapchat Export"
2. **CTA button**: "Start Processing" vs. "Upload Now" vs. "Get Started"
3. **Feature bullets**: Current 4-item list vs. 3-item (less is more) vs. 6-item (more detail)
4. **Upload options**: Checkbox defaults (all ON vs. smart defaults based on user plan tier)
5. **Empty states**: Blank canvas vs. inspirational copy

---

## FUTURE COPY NEEDS

- **Onboarding email**: Welcome, explain 30-day retention, link to support.
- **Confirmation email**: Job complete, download link, keep for 7 days.
- **Error escalation email**: Job failed, troubleshooting steps, contact support.
- **Upgrade upsell**: "You're running low on storage. Upgrade to Plus for 50 GB."
- **In-app help**: Tooltip on "Match Rate," "Phase 2: Match," "GPS Coverage" (context-sensitive).
- **FAQ / Knowledge Base**: "Why didn't my chats match?" "What's EXIF?" "How do I import to Immich?"

