# Agent A's 3 New Stories (Emerged from Round 2 Debate)

**Author**: Agent A (New User Advocate)
**Reason**: These stories emerged from synthesizing Agent B (Power User) and Agent C (Product Strategist) perspectives. They fill critical gaps in the onboarding and error-handling experience for new users.
**Date**: 2026-02-24

---

## New Story A1: Guided Results Page Tour for First-Time Users

**Title**: Guided Results Page Tour for First-Time Users

**As a** new user viewing Results page for the first time
**I want to** see a guided tour of what each section means (Matches | Assets | Chats | Stats)
**So that** I understand the data I recovered and feel confident downloading

---

### Current State
User completes upload, job processes successfully, and lands on Results page. They see:
- Sticky header with 11 buttons (Results | Download | Corrections | Reprocess | ... etc.)
- Tabs: Summary | Matches | Assets | Chats | Timeline | etc.
- Each tab shows tables, stats, and options unfamiliar to new users

**New user reaction**: "What is a 'Matches' tab? What does 'Confidence' mean? Why are there 347 matches and only 123 assets? Am I supposed to do something?"

---

### Proposed Fix

**On first visit to Results page, show a guided tour overlay** (low-key, non-intrusive):

1. **Tour Step 1 (Summary tab)**:
   - Highlight: "Here are your recovered memories: 347 photos, 45 videos, 89 chat exports"
   - Tooltip: "This is what Snatched found in your Snapchat export. Each item is a 'match' - a memory Snatched confidently recovered."
   - Show example confidence score (87%) with simple explanation: "Confidence shows how sure we are this is the right memory."

2. **Tour Step 2 (Matches tab)**:
   - Highlight: Matches table
   - Tooltip: "Here are all your recovered memories, sorted by confidence. Confidence is how sure Snatched is about the match. You can download all of them, or pick specific ones."

3. **Tour Step 3 (Assets tab)**:
   - Highlight: Assets table
   - Tooltip: "These are the actual files (photos, videos) from your Snapchat export. Download them individually or as a ZIP."

4. **Tour Step 4 (Chats tab)**:
   - Highlight: Chats table
   - Tooltip: "Your Snapchat conversations, exported as images. Snatched extracted them from your export and is bundling them with your other memories."

5. **Tour Step 5 (Download)**:
   - Highlight: [Download] button
   - Tooltip: "Ready to go? Click here to download all your recovered memories as a ZIP file. You'll have 30 days to re-download if needed."

---

### Implementation Details

- **When shown**: Only on first visit to `/results/{job_id}` for each user (check `user.results_tour_completed` flag)
- **Skippable**: [Skip Tour] button always visible, or close after tooltip reveals 5 seconds (auto-advance)
- **Style**: Overlay with dark background, tooltip boxes point to relevant UI elements (use Popper.js or similar)
- **Accessibility**: ARIA labels on tooltips, keyboard: Tab = next tooltip, Escape = skip
- **Mobile**: Full-screen modal version (not popovers), touch-friendly navigation
- **Repeat users**: Never show again (unless user requests in ?, but default: hidden after first visit)
- **Tour completion**: After Step 5, show: "✓ You're ready to download. [Dismiss]"

---

### Database Changes
```sql
ALTER TABLE users ADD COLUMN results_tour_completed BOOLEAN DEFAULT FALSE;
ALTER TABLE job_results ADD COLUMN user_tour_shown_at TIMESTAMP;
```

---

### API/Routes
- GET `/api/users/me/has-seen-results-tour` → returns boolean
- PATCH `/api/users/me/results-tour-completed` → marks as completed

---

### Benefits
- **New users understand their data** — No more confusion about "matches" vs "assets"
- **Reduces support tickets** — "What's a confidence score?" becomes unnecessary
- **Builds confidence** — User feels guided and understands what they've accomplished
- **One-time UX** — Not intrusive; only shown once per user

---

### Priority
**P1 (High)** — Part of Phase 1 MVP. Critical for new user confidence.

---

---

## New Story A2: Empty States & Progressive Education

**Title**: Empty States & Progressive Education (Before First Upload & After Job Starts)

**As a** first-time user on an empty Dashboard or watching a job process
**I want to** see clear guidance on what to do next, not just blank space
**So that** I know my first action is to upload, and I understand the job is progressing

---

### Current State

**Empty Dashboard (before first upload)**:
- Stat cards: "0 Jobs | 0 Total Recovered | 0 Storage Used"
- Job list: Empty
- User doesn't know what to do next

**Running Job**:
- Minimal indication of progress (assumed: some status indicator exists)
- User doesn't understand what "Phase 2/4" means

---

### Proposed Fix

#### Part 1: Empty Dashboard Welcome State

**Show a friendly, action-oriented empty state:**

```
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║                    WELCOME TO SNATCHED                         ║
║                                                                ║
║     Rescue your Snapchat memories before they're gone.        ║
║                                                                ║
║                📥 [START YOUR FIRST EXPORT]                    ║
║                                                                ║
║     ✓ We process your data safely (no tracking, no ads)       ║
║     ✓ You keep all your memories                              ║
║     ✓ Free to try, 30-day retention                           ║
║                                                                ║
║     [How It Works ▼]  [Privacy Policy]  [Questions? Chat]     ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
```

- **Design**: Center, large, welcoming, not empty-feeling
- **CTA**: [START YOUR FIRST EXPORT] button (links to `/upload`)
- **Reassurance**: 3 bullet points addressing fears (safety, ownership, cost)
- **Help**: Links to how-it-works and support

---

#### Part 2: First Job Progress State

**When user uploads and job starts processing:**

Instead of generic "Phase 2 of 4," show:

```
╔════════════════════════════════════════════════════════════════╗
║  Your job is processing...                    [Cancel] [Pause] ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  📥 PHASE 1: Ingest     [✓ Complete, 2.8 GB processed]       ║
║  🔍 PHASE 2: Match      [In progress... 34% complete]        ║
║     → Matching 5,234 photos to your Snapchat metadata        ║
║     → Estimated 2 minutes remaining                           ║
║                                                                ║
║  🎨 PHASE 3: Enrich     [Waiting...]                         ║
║     → Will add GPS tags, timestamps, and captions            ║
║                                                                ║
║  📦 PHASE 4: Export     [Waiting...]                         ║
║     → Will bundle everything into downloadable files         ║
║                                                                ║
║  💡 What's happening?                                         ║
║     Snatched is rebuilding your memories from Snapchat data. ║
║     Each phase extracts different metadata and adds it back. ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
```

- **Design**: Shows progress (bars, percentages, checkmarks)
- **Education**: Each phase has 1-2 lines explaining what's happening
- **Transparency**: Estimated time remaining, what data is being processed
- **Control**: [Cancel] or [Pause] buttons for user control

---

#### Part 3: Completed Job (Before Download)

**When job completes, before user clicks Download:**

```
╔════════════════════════════════════════════════════════════════╗
║  ✓ MISSION ACCOMPLISHED                                       ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  You recovered: 347 photos | 45 videos | 89 chats            ║
║                                                                ║
║  📍 GPS Data: 234 locations tagged (67%)                      ║
║  📅 Timestamps: All photos timestamped                        ║
║  💬 Chats: Exported as 15 PNG images                          ║
║                                                                ║
║                   [📥 DOWNLOAD YOUR MEMORIES]                 ║
║                                                                ║
║  Your files will be available for 30 days.                    ║
║  Pro users get 180-day retention. [Learn about Pro]           ║
║                                                                ║
║  [What's Next?]  [View Details]                              ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
```

- **Celebration**: Checkmark, "Mission Accomplished" header
- **Summary**: Key metrics (photos, videos, chats) + success rates (GPS %, etc.)
- **Data ownership**: Emphasis: "You keep all your memories"
- **CTA**: [DOWNLOAD] button (primary, snap-yellow)
- **Next steps**: Guidance on what to do now

---

### Implementation Details

- **First empty state**: Conditional Jinja2 template: `{% if user.jobs.count == 0 %}`
- **Job progress page**: New route `/jobs/{job_id}/progress` (or expand existing progress endpoint)
- **Completion state**: Conditional on Results page load: `{% if job.status == 'completed' and not user.has_seen_completion_state %}`
- **Database**: Add `user.has_seen_completion_state` flag (per job)
- **SSE (Server-Sent Events)**: Real-time phase progress updates to avoid polling

---

### Benefits
- **Reduces user anxiety** — Clear expectations (what's happening, how long)
- **Improves confidence** — User understands the value they're getting
- **Celebrates achievement** — Completion state feels rewarding, not clinical
- **Prevents support tickets** — "What does Phase 2 mean?" answered by UI
- **Guides next action** — User never wonders "now what?"

---

### Priority
**P1 (High)** — Part of Phase 1 MVP. Critical for onboarding completion and user confidence.

---

---

## New Story A3: Error Recovery & Empathy

**Title**: Error Recovery & Empathy (All Errors Speak Plain English + Offer Help)

**As a** user whose upload failed, job crashed, or feature isn't available
**I want to** see a clear explanation (in plain English, not error codes) + next steps
**So that** I don't feel helpless or abandoned

---

### Current State

**Example error today**:
- "413 Payload Too Large"
- User doesn't know what "payload" means
- No next steps offered
- Support link hidden in docs

**User reaction**: Frustration, potential abandonment.

---

### Proposed Fix

**All error states follow a formula:**

```
[⚠️ Icon]  WHAT HAPPENED
────────────────────────────────

Your file is too large.

WHY IT HAPPENED
Your Snapchat export (2.8 GB) exceeds the Free tier limit (2 GB max).

WHAT YOU CAN DO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Option 1: Reduce your file size
  Remove old chats or photos from your Snapchat export before uploading.
  [Instructions →]

Option 2: Upgrade to Pro
  Pro plan supports files up to 25 GB.
  [Upgrade Now]  [See All Plans]

Option 3: Contact Support
  We're here to help. Reply to this email or [open a ticket].
  Typical response time: 2 hours.

───────────────────────────────────────────────────────────────────
Error ID: upload_413_file_too_large (for support reference)
```

---

### Key Principles for All Errors

1. **What Happened** (plain English, not error codes)
   - ✓ "Your file is too large"
   - ✗ "413 Payload Too Large"

2. **Why It Happened** (context, not blame)
   - ✓ "Your Snapchat export (2.8 GB) exceeds the Free tier limit"
   - ✗ "Multipart/form-data exceeded limits"

3. **What Now** (3-5 actionable options)
   - ✓ [Reduce file] [Upgrade] [Contact Support]
   - ✗ "Please try again"

4. **Support Link** (always visible)
   - ✓ "Contact Support [link] | 2-hour response time"
   - ✗ Hidden in docs or FAQs

5. **Tone** (empathy, not blame)
   - ✓ "Let's get this fixed together"
   - ✗ "You did this wrong"

---

### Error Types & Examples

#### Upload Errors

**File Too Large**:
```
Your file is too large.
Your Snapchat export (2.8 GB) exceeds the Free tier limit (2 GB max).

Option 1: Reduce your file size [Instructions]
Option 2: Upgrade to Pro ($4.99/mo, 25 GB limit) [Upgrade]
Option 3: Contact Support [Email]
```

**Invalid Format**:
```
We couldn't read your file.
Snatched expects a .ZIP file from "Settings > My Data" in Snapchat.
Make sure you downloaded the right file.

Option 1: Download your Snapchat data again [How to →]
Option 2: Try a different browser or device
Option 3: Contact Support if the problem persists [Email]
```

**Upload Interrupted**:
```
Your upload was interrupted.
This can happen if your connection dropped or the server was busy.

Option 1: Retry the same file [Retry]
Option 2: Check your internet connection, then try again
Option 3: Contact Support if this keeps happening [Email]
```

#### Job Processing Errors

**Job Crashed**:
```
Your job encountered an error and stopped.
This is rare, and we've logged the issue for investigation.

Option 1: Retry the same job [Retry]
Option 2: Start a new upload with the same file
Option 3: Contact Support [Email] with Job ID: #12345
```

**Feature Not Available**:
```
This feature is for Pro users.
GPS Correction helps you fix locations Snatched couldn't find automatically.

Option 1: Upgrade to Pro and unlock GPS Correction [Upgrade]
Option 2: Learn more about Pro features [See All Plans]
Option 3: Ask Support if you need a different plan [Email]
```

**Rate Limited** (power user too many requests):
```
You're being rate-limited.
You've made too many API requests in the last hour.
Pro users get higher limits.

Option 1: Wait 1 hour, then try again
Option 2: Upgrade to Pro for higher rate limits [Upgrade]
Option 3: Contact Support for enterprise limits [Email]
```

---

### Implementation Details

#### Error Component (Reusable)
```
<ErrorCard>
  <ErrorTitle>What Happened</ErrorTitle>
  <ErrorMessage>{message}</ErrorMessage>

  <ErrorExplanation>Why It Happened</ErrorExplanation>
  <ErrorReason>{reason}</ErrorReason>

  <ErrorActions>
    {actions.map(action => (
      <Button>{action.label}</Button>
    ))}
  </ErrorActions>

  <ErrorSupport>
    Contact Support [link] | Response time: 2 hours
  </ErrorSupport>

  <ErrorId>Error ID: {error_code}</ErrorId>
</ErrorCard>
```

#### Database (Error Log)
```sql
CREATE TABLE error_logs (
  id UUID,
  user_id UUID,
  error_code VARCHAR(50),  -- upload_413_file_too_large
  message TEXT,             -- "Your file is too large"
  reason TEXT,              -- "Your export (2.8 GB) exceeds Free limit"
  actions JSONB,            -- [{label, link, type}]
  contact_support BOOLEAN,  -- true for all errors
  created_at TIMESTAMP
);
```

#### Copy Audit Template
All error messages should follow:
- Friendly tone (no jargon)
- User-centric language ("you" not "system")
- 1-2 sentence explanation (not a novel)
- 3-5 actionable options
- Support link always visible

---

### Benefits
- **Reduces frustration** — User understands what went wrong
- **Empowers recovery** — Clear options, not dead ends
- **Lowers support burden** — Errors guide users to solutions (reduces tickets by ~30%)
- **Builds trust** — Transparent communication = trustworthy product
- **Accessible** — Plain English > technical jargon

---

### Priority
**P1 (High)** — Part of Phase 1 MVP. Errors are unavoidable; make them helpful.

---

---

## Summary: Why These 3 Stories Emerged

| Story | Emerged From | Solves |
|-------|--------------|--------|
| **A1: Guided Results Tour** | Seeing B's 11 buttons on Results page + C's push for feature discoverability | New user confusion about what "matches" and "confidence" mean |
| **A2: Empty States & Progress** | Seeing B's focus on dashboard efficiency + C's focus on conversion | User anxiety during processing and not knowing "what's next" after download |
| **A3: Error Recovery** | C's brand voice consistency + B's automation features that can fail | User abandonment when errors occur; support tickets for jargon confusion |

All three fill critical **new user experience gaps** that neither B nor C explicitly addressed, but both would benefit from (B: less support noise; C: better retention and conversion).

---

## Implementation Priority

- **A1 (Guided Results Tour)**: Phase 1 — Ship with first download feature
- **A2 (Empty States)**: Phase 1 — Ship with onboarding
- **A3 (Error Recovery)**: Phase 1 — Audit and fix all error copy before launch

---

**Author**: Agent A (New User Advocate)
**Date**: 2026-02-24
**Status**: Ready for consensus approval
