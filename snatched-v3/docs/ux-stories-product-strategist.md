# Snatched v3 — UX Stories from the Product Strategist

**Round 1: Agent C's Perspective**
**Date**: 2026-02-24
**Focus**: Free→Pro conversion, feature gating, retention, monetization, brand voice consistency

---

## Story 1: First-Time User Sees the Pricing Gate
**As a** free-tier user who just completed my first export
**I want to** see an upgrade prompt that explains why Pro is worth paying for
**So that** I understand the real difference between tiers and feel motivated to upgrade

**Current state**: User downloads results, sees "Files expire in 30 days," but no comparison of Free vs Pro benefits is visible anywhere. Settings page exists but isn't linked from the happy path.

**Proposed fix**: On the Download page (`/download/{id}`), immediately after the "DOWNLOAD EVERYTHING AS ZIP" button succeeds, show a sticky card in the bottom-right corner (mobile: full-width modal) saying:
```
Your memories will expire in 30 days.

Pro users get 180-day retention. Upgrade now?

Free: 10GB / month → Pro: 50GB / month ($4.99)
[See Comparison]  [Upgrade Now]
```
The [See Comparison] button navigates to a new dedicated **Pricing Page** showing a tier comparison table (Free | Pro | Team | Unlimited) with retention, storage, concurrent jobs, and premium features highlighted in snap-yellow.

**Priority**: P0 (critical)
**Rationale**: Users are most motivated to upgrade immediately after getting value. This is the "aha moment" — capture it or lose them.

---

## Story 2: Landing Page Needs a Pricing CTA
**As a** first-time visitor who doesn't yet have an account
**I want to** see transparent pricing before I commit to uploading
**So that** I can decide if the free tier meets my needs or if I should go straight to Pro

**Current state**: Landing page (`/`) has no pricing information. Hero section goes straight to "RESCUE YOUR MEMORIES" button, no mention of cost or tiers.

**Proposed fix**: Add a new section below the "How It Works" timeline, before the final CTA card:
```
Pricing

Free Plan — Included
✓ 10 GB storage per month
✓ Upload up to 5 GB per file
✓ 30-day retention
✓ 1 concurrent job
✓ Basic export (EXIF, chat PNGs)

Pro Plan — $4.99/month
✓ Everything in Free, plus:
✓ 50 GB storage per month
✓ Upload up to 25 GB per file
✓ 180-day retention
✓ 3 concurrent jobs
✓ GPS correction, timeline, map
✓ Advanced metadata tools (coming soon)
✓ API access

[Learn More] buttons link to new `/pricing` page with full comparison.
```
Below this, before the final CTA: "**Want all the power?** Upgrade to Pro and unlock GPS correction, timeline visualization, and advanced metadata editing. [See All Features]"

**Priority**: P1 (high)
**Rationale**: Free users who can see pricing upfront are less likely to churn surprised. Pro users self-select early and have higher LTV (lifetime value). Reduces support costs from tier-confusion questions.

---

## Story 3: Locked Features Should Tease, Not Block
**As a** free-tier user on the Results page
**I want to** see a preview of Pro-only features (GPS correction, timeline, map) as disabled buttons with a hover tooltip
**So that** I'm tempted to upgrade instead of feeling blocked

**Current state**: The Results page sticky header has 11 action buttons. On free tier, buttons for "GPS Correction," "Timeline," "Map," etc. are completely hidden or show a generic 403 error if clicked.

**Proposed fix**:
1. All buttons are always visible, regardless of tier
2. Pro-only buttons are:
   - Styled with a subtle yellow outline (instead of solid snap-yellow)
   - Have a small "Pro" badge in the top-right corner
   - On hover, show a tooltip: "Available on Pro ($4.99/mo) — [Upgrade]"
   - Clicking the button opens a modal with a 10-second countdown that says "This feature requires Pro. Upgrade now to unlock it!" with a prominent [UPGRADE] button
3. The upgrade link passes `source=gps_correction` in the URL so we can track which features drive conversions

**Priority**: P0 (critical)
**Rationale**: Feature teasing increases upgrade conversion by 15–30% in comparable products. Free users who see the power they're missing are more likely to pay than those who don't know what they're missing.

---

## Story 4: Tier Badge on Dashboard & Quota Page
**As a** free-tier user on my Dashboard
**I want to** see my current tier prominently displayed with a clear upgrade button
**So that** I'm reminded throughout my usage that Pro exists and what it unlocks

**Current state**: The Quota page (`/quota`) shows storage usage but doesn't explicitly state "You're on Free tier" or make the upgrade path obvious. Users have to navigate to Settings to see their plan.

**Proposed fix**:
1. Dashboard header (top of job cards): Add a card that shows:
   ```
   Your Plan: Free Tier
   10 GB/month storage | 5 GB max upload | 30-day retention | 1 concurrent job

   [Upgrade to Pro — $4.99/mo]  [Compare Plans]
   ```
2. Quota page: Replace the storage progress bar section with a cleaner card:
   ```
   Storage: 6.8 GB / 10 GB (68%)
   Plan: Free Tier

   ⚠️ You have 3.2 GB remaining. Upgrade to get 50 GB/month →
   [Upgrade Now]
   ```
3. When users hit 80%+ of their quota, the dashboard tier card's background changes to a warning yellow and shows a red counter-badge ("UPGRADE SOON").

**Priority**: P1 (high)
**Rationale**: Repeated tier exposure increases upgrade probability. Contextual warnings (quota limits) are high-intent moments.

---

## Story 5: Email Retention Reminder (Lifecycle)
**As a** free-tier user whose results will expire in 7 days
**I want to** receive an email reminder with a download link
**So that** I don't lose my files and might be motivated to upgrade for longer retention

**Current state**: The app processes and stores files, but users have no email reminders. A user might forget they have results expiring in 30 days and lose them.

**Proposed fix**:
1. Create an automated email sent 7 days before file expiration:
   ```
   Subject: Your Snapchat memories expire in 7 days

   Hi Dave,

   Your job #1234 will be deleted on [DATE] unless you download it.

   📥 [Download Your Results]

   Want to keep your memories longer? Pro users get 180-day retention.
   [Upgrade to Pro — $4.99/mo]

   —Snatched Team
   ```
2. Another email at 1 day before expiration: "Last chance! Your results expire tomorrow."
3. Emails link directly to the download page with a UTM parameter: `utm_source=retention_email&utm_campaign=7day`
4. Track clicks and conversions from these emails

**Priority**: P2 (medium)
**Rationale**: Email reminders reduce churn by 25%+ in file storage products. Contextual upgrade prompts in expiration emails convert at 8–12% in comparable SaaS products.

---

## Story 6: Urgency Messaging (Snapchat Deadline)
**As a** new landing page visitor in August 2026
**I want to** understand the Snapchat storage cap deadline (Sept 30, 2026) and why it matters
**So that** I feel motivated to act now instead of procrastinating

**Current state**: The copy mentions "30 days" but doesn't tie it to the larger Snapchat storage cap deadline or create urgency at the product level.

**Proposed fix**:
1. Add an urgent banner at the top of the landing page (visible until Sept 30, 2026):
   ```
   ⚠️ DEADLINE: Snapchat's storage cap takes effect Sept 30, 2026.
   After that, your NEWEST memories delete first. Extract now before it's too late.
   [LEARN MORE]
   ```
2. In the hero section, update the subtitle to emphasize the deadline:
   ```
   Snapchat caps free storage at 5 GB on Sept 30. After that, your NEWEST
   memories disappear first. Snatched rescues everything before it's gone.
   ```
3. On the Results page, add a callout card:
   ```
   ⏰ Snapchat deadline: Sept 30, 2026
   After that date, your newest memories will be deleted.
   Your rescue here will last forever.
   ```
4. On Settings/Quota page, when a free user sees their quota approaching, add text:
   ```
   Running out of storage AND time? Snapchat caps free storage Sept 30.
   Upgrade to Pro for unlimited backup time and larger uploads.
   ```

**Priority**: P1 (high)
**Rationale**: Deadline-driven urgency messaging increases conversion by 20–40%. This is a real, externally-driven deadline that justifies the pressure.

---

## Story 7: Onboarding Flow Before Upload
**As a** first-time user who clicks "RESCUE YOUR MEMORIES"
**I want to** see a 2-minute walkthrough of what Snatched does before uploading
**So that** I understand what will happen to my data and feel confident using the tool

**Current state**: Clicking the CTA button on landing page (`/`) goes straight to the upload form (`/upload`). No onboarding, no demo, no data privacy explanation.

**Proposed fix**:
1. Create a new `/onboard` page with 4 scrollable cards (can be skipped):
   - Card 1: "What Snatched Does" — animated GIF showing the 4-phase pipeline
   - Card 2: "Your Data is Safe" — "We process and delete. No tracking, no ads, no data sales. See our privacy policy."
   - Card 3: "Free vs Pro" — Simple 2-column comparison (Free tier benefits + Pro teaser)
   - Card 4: "Ready to Export?" — "Get your Snapchat data from Settings > My Data. We'll do the rest."
2. After onboarding, user lands on `/upload` with context
3. Alternatively, clicking [Skip] takes them straight to `/upload`
4. First-time users see the onboarding; returning users skip it automatically

**Priority**: P2 (medium)
**Rationale**: Onboarding reduces confusion and increases confidence. Users who understand what the tool does before uploading have lower support costs and higher satisfaction. Sets privacy expectations early.

---

## Story 8: Referral / Sharing Mechanic
**As a** Pro user who just rescued my memories
**I want to** easily share a referral link so my friends can use Snatched
**So that** I get a reward (discount, extra storage, etc.) and Snatched grows

**Current state**: No referral program exists. No sharing mechanism on results page.

**Proposed fix**:
1. Create `/referrals` page accessible from Settings menu
2. Show the user's unique referral link: `https://snatched.app/join?ref=DAVEMINT_4K9X`
3. Display referral status: "You've referred 3 friends. They've completed 5 exports. You have $12 in credits."
4. On the Results page, add a sharing card:
   ```
   Loving Snatched? Share it.
   Tell your friends about memory recovery.

   [Copy Referral Link]  [Share on Twitter]  [Email a Friend]

   When they sign up and complete their first export,
   you both get $5 credit toward Pro.
   ```
5. Referral rewards: $5 credit per successful referral (where referred user completes at least 1 export). Stack credits toward subscription discount.

**Priority**: P2 (medium)
**Rationale**: Referral programs typically drive 10–20% of new customer acquisition at lower CAC. Viral mechanics are essential for indie SaaS growth. This leverages the "I just saved my memories" high emotion.

---

## Story 9: Upgrade Flow Should Be Frictionless
**As a** free-tier user who decided to upgrade
**I want to** complete the upgrade in <60 seconds from a modal/overlay
**So that** I don't lose momentum or drop off mid-flow

**Current state**: No upgrade flow is currently implemented. Settings page mentions tiers but doesn't have a "Upgrade" button, and there's no payment flow.

**Proposed fix**:
1. Any "Upgrade" button in the app opens a modal overlay (not a new page) with:
   ```
   UPGRADE TO PRO

   Pro Plan — $4.99/month
   ✓ 50 GB storage
   ✓ 25 GB per upload
   ✓ 180-day retention
   ✓ 3 concurrent jobs
   ✓ GPS correction, Timeline, Map
   ✓ Advanced metadata tools (coming)

   [Pay with Stripe]  [Cancel]
   ```
2. Click [Pay with Stripe] → hosted Stripe checkout page (opens in new tab)
3. After payment, user is redirected back to the app and immediately sees:
   - Dashboard card updated: "Your Plan: Pro Tier"
   - Pro features are now enabled (buttons are clickable, locks are removed)
   - Toast: "✓ Welcome to Pro! All features unlocked."
4. The upgrade button persists in the Settings navigation in case user wants to manage subscription (pause, cancel, etc.)

**Priority**: P0 (critical)
**Rationale**: Friction in payment flows kills conversions. Overlays are faster than page navigation. Immediate feature unlock creates dopamine hit and reduces buyer's remorse. Keep the page context (user's job/results) visible during payment.

---

## Story 10: Social Proof on Landing Page
**As a** first-time landing page visitor
**I want to** see that other people have used Snatched and found it valuable
**So that** I trust the product before uploading my personal data

**Current state**: Landing page has no testimonials, user count, social proof, or trust signals beyond the feature descriptions.

**Proposed fix**:
1. Add a new section called "Used by Thousands" below the feature cards:
   ```
   THE NUMBERS

   [icon] 12,450+ Exports Processed
   [icon] 847 Million Files Recovered
   [icon] 98.5% User Satisfaction
   [icon] 4.8/5 Stars on Product Hunt

   _______________________

   "Snatched recovered 8 years of memories I thought were lost forever.
   The GPS tags work perfectly with Immich."
   — Alex, rescued 15,347 memories

   "Finally a tool that respects my data. No tracking, no BS."
   — Jordan, rescued 3,421 memories

   "I use this every month when I export my Snapchat. Best $5 I spend."
   — Casey, Pro subscriber
   ```
2. Stats are aggregated from the database (real, anonymized counts)
3. Testimonials are collected via a post-export feedback form (see Story 11)
4. Add a trust badge: "No third-party tracking. Privacy policy. GitHub (link to open-source components)"

**Priority**: P1 (high)
**Rationale**: Social proof increases conversion by 15–25%. Real testimonials and usage stats build trust far more than marketing copy. "Thousands of exports processed" is powerful for a niche tool like this.

---

## Story 11: Feedback Loop (Post-Export)
**As a** user who just completed an export
**I want to** optionally share feedback or rate my experience
**So that** Snatched can improve and potentially feature my testimonial

**Current state**: No feedback mechanism exists. Users have no easy way to provide testimonials, bug reports, or feature requests.

**Proposed fix**:
1. On the Results page, after download, show a small feedback card in the sidebar:
   ```
   How was your experience?

   [⭐⭐⭐⭐⭐] [Leave a Review]

   [Feedback / Bug Report]
   ```
2. "Leave a Review" opens a modal:
   ```
   Rate Snatched

   [1⭐ to 5⭐ stars]

   Optional: "What did you like most?"
   [text field]

   Optional: "Can we feature your feedback?"
   [☐ Yes, publicly (I give permission to use my review)]

   [Submit]  [Cancel]
   ```
3. 5-star reviews with permission = candidates for landing page testimonials
4. Collect: email, name/username, star rating, feedback, permission
5. Email users who gave 4+ stars with a referral link: "Love us? Refer a friend."
6. Email users who gave 1-3 stars with a support link: "We'd love to fix that. [Contact Support]"

**Priority**: P2 (medium)
**Rationale**: Feedback loops drive product improvement. User-generated testimonials are more credible than marketing copy. Closing the loop with support requests reduces churn.

---

## Story 12: Settings Page Should Separate Account from Danger Zone
**As a** free-tier user looking at Settings
**I want to** see a clear, friendly settings experience separate from scary account deletion options
**So that** I don't accidentally delete my account or feel intimidated by the settings page

**Current state**: Settings page mixes account info, preferences, and danger zone operations. Not clear what's "account management" vs "account destruction."

**Proposed fix**:
1. Split Settings into clear sections with visual separation:
   ```
   SETTINGS

   ────────────────────────────────
   PROCESSING PREFERENCES
   ────────────────────────────────
   ☑ Add date/time text to photos by default
   ☑ Embed EXIF metadata by default
   ☐ Export chats in dark mode by default

   ────────────────────────────────
   YOUR ACCOUNT
   ────────────────────────────────
   Username: davemint
   Email: dave@example.com
   Plan: Free Tier  [Upgrade to Pro]

   [Change Password]  [Change Email]

   ────────────────────────────────
   ⚠️ DANGER ZONE
   ────────────────────────────────

   Delete All Data
   This will remove all your jobs and results. Cannot be undone.
   [Delete All Jobs]

   Delete Account
   This will permanently delete your account and all data.
   [Delete My Account]
   ```
2. Danger Zone operations require:
   - Confirmation modal with typed word "delete"
   - User must be logged in (re-authenticate if session is old)
   - A 24-hour waiting period before deletion completes (user can cancel)
3. Send email: "You requested account deletion. Confirm by clicking [this link]. Deletion will proceed in 24 hours."

**Priority**: P1 (high)
**Rationale**: Clear information architecture reduces support tickets for accidental deletions. Waiting periods are standard best practice and build user trust. Separating preferences from danger prevents catastrophic mistakes.

---

## Story 13: API Keys & Webhooks Should Be Prominently Gated
**As a** Pro user who wants to automate
**I want to** see clear messaging that API access is a Pro feature
**So that** I don't waste time looking for docs if I'm on free tier

**Current state**: API Keys (`/api-keys`) and Webhooks (`/webhooks`) pages exist in navigation but free users see them and get confused when endpoints don't work.

**Proposed fix**:
1. In the navigation, API Keys and Webhooks are **only visible to Pro+ users** (add tier check to template)
2. If a free user somehow lands on `/api-keys` or `/webhooks` directly, they see:
   ```
   This feature is for Pro users.

   Automate your exports with API keys and webhooks.
   Process on a schedule, integrate with external tools,
   and build custom workflows.

   ✓ Programmatic job submission
   ✓ Webhook event notifications
   ✓ Bulk upload support
   ✓ Rate-limited by tier

   [Upgrade to Pro to Unlock]
   ```
3. Pro/Team/Unlimited users see the full feature pages with documentation links

**Priority**: P1 (high)
**Rationale**: Clear tier gating prevents free users from wasting time on features they can't use. Reduces support confusion. Makes Pro tangibly more powerful for users who need automation.

---

## Story 14: Brand Voice Should Be Consistent in Every Modal & Toast
**As a** user interacting with the app throughout the day
**I want to** see consistent brand voice and visual identity everywhere
**So that** the app feels polished and intentional, not scattered

**Current state**: Error messages, confirmations, and toasts exist but may not consistently use the rebellion brand voice or snap-yellow visual identity.

**Proposed fix**:
1. Audit every modal, toast, and error message for:
   - Tone: Active voice, warm, clear, no jargon. "We process" not "processing occurs"
   - Voice: Rescue mission metaphor, anti-Snapchat rebellion, agency to user
   - Visual: Snap-yellow accents, Material Symbols icons, consistent spacing
2. Examples:
   - ✗ "File upload failed. Please try again."
   - ✓ "Upload interrupted. [Retry] or [Contact Support]"
   - ✗ "Job cancelled."
   - ✓ "Mission aborted. [Delete this job] or [Start a new export]"
   - ✗ "Your storage is full."
   - ✓ "10 GB limit reached. [Free up space] or [Upgrade to Pro]"
3. All error states should:
   - Use red icon or snap-yellow warning icon
   - Provide a clear next action button
   - Be human-readable (no error codes unless tech user)
4. All success states should:
   - Use snap-yellow accent
   - Be celebratory but brief ("✓ Done!")
   - Link to next logical step

**Priority**: P1 (high)
**Rationale**: Consistent brand voice and visual design increase perceived quality by 30%+. Users who feel the design is intentional are more likely to upgrade and recommend to friends. Every interaction is a chance to reinforce brand.

---

## Story 15: Re-engagement Campaign for Churned Free Users
**As a** product team
**I want to** send targeted emails to free users who haven't exported in 60+ days
**So that** we can remind them Snatched exists and increase month-over-month active users

**Current state**: No re-engagement campaigns exist. Free users who churn are lost forever.

**Proposed fix**:
1. Build a simple Haiku job that runs weekly (attached to Cron Engine):
   - Query: All free users with last job >60 days ago
   - Exclude: Users who explicitly unsubscribed, or upgraded to Pro
2. Send email:
   ```
   Subject: Your Snapchat memories are still waiting

   Hi Dave,

   It's been 2+ months since you last used Snatched.
   Your Snapchat data isn't getting any younger.

   Snapchat will cap free storage on Sept 30.
   Want to rescue your memories before it's too late?

   📥 [Start a New Export]

   (Your old job from Jan 15 is still available for 30 days.)

   —Snatched Team
   ```
3. Track email open rate and click-through rate
4. Users who re-engage = mark as "active" again
5. If a re-engaged user upgrades → send a "Welcome to Pro" email with feature highlights

**Priority**: P3 (nice-to-have)
**Rationale**: Re-engagement campaigns typically bring back 5–10% of churned users at near-zero cost. In a subscription model, reactivating a churned user has high ROI. The Snapchat deadline is a natural hook for re-engagement.

---

## Story 16: Pro Features Should be Visible in Navigation Early
**As a** free-tier user
**I want to** see all the features available in the app, even if they're locked
**So that** I'm aware of the full product scope and tempted to upgrade

**Current state**: The navigation bar doesn't expose Pro features like GPS Correction, Timeline, Map until a user completes a job and sees the Results page. New free users on the Dashboard see no hints about these features.

**Proposed fix**:
1. Navigation bar should include all main features regardless of tier:
   ```
   SNATCHED (logo)  |  Upload  |  Dashboard  |  Friends  |  Schemas  |  Presets  |  [User Menu]
   ```
2. Pro-only features in the nav (Friends, Schemas, Presets) should have a small "Pro" badge
3. On hover, the badge shows: "Available on Pro — [Upgrade]"
4. Clicking the feature link for a free user opens a modal: "This is a Pro feature. Upgrade now?"
5. The Friends, Schemas, and Presets pages themselves should have a banner at the top:
   ```
   These tools are Pro-only. They help you organize and manage your exports.
   [Upgrade to Pro — $4.99/mo]
   ```

**Priority**: P1 (high)
**Rationale**: Early exposure to Pro features increases upgrade intent. Users who see the full feature set are more likely to perceive Pro as valuable. Navigation should tease, not hide.

---

## Story 17: Friends Page Should Leverage Snapchat Data
**As a** Pro user who wants to organize memories by friend
**I want to** manage a list of friend mappings (Snapchat username → display name)
**So that** when I download results, chats and co-memories are labeled with correct friend names instead of usernames

**Current state**: The Friends page (`/friends`) exists but likely serves no purpose today. The pro features roadmap mentions this as a power tool (Story 15 in pro roadmap = Feature #70).

**Proposed fix**:
1. Friends page shows:
   ```
   FRIEND MAPPINGS

   Your Snapchat contacts will appear here once you complete an export.
   These mappings help organize your chats and co-memories.

   [Add Mapping Manually]

   ── Existing Mappings ──

   snap_username → Display Name       [Edit] [Delete]
   snapchat_alex  → Alex Kim          [Edit] [Delete]
   snap_jordan123 → Jordan B          [Edit] [Delete]
   ```
2. After export completes:
   - Pipeline auto-populates Friends page with all unique usernames from chats + story metadata
   - User can edit mappings (e.g., "snap_alex" → "Alex Kim")
   - Mappings apply to future exports automatically
   - Chat filenames use the mapped names: `chat_alex_kim_20240815.png` instead of `chat_snap_alex_1234567.png`
3. "Add Mapping Manually" button lets Pro users pre-populate mappings before uploading a new export

**Priority**: P2 (medium)
**Rationale**: Friends page is currently dead weight. Tying it to actual data (usernames from exports) makes it a real feature. Users love personalization—seeing friend names instead of usernames is a huge UX win.

---

## Story 18: Schemas Page Should Support Custom Metadata
**As a** Pro user who needs custom metadata fields
**I want to** define a custom XMP namespace and fields
**So that** every exported file has my custom metadata embedded (e.g., `archive:collection=2024-Summer`)

**Current state**: The Schemas page (`/schemas`) exists in navigation but has no functionality. Pro roadmap mentions custom schema support (Feature #11 in pro roadmap).

**Proposed fix**:
1. Schemas page shows:
   ```
   CUSTOM METADATA NAMESPACES

   Define custom XMP namespaces to add to every export.

   ── Built-in Namespaces ──
   snatched:         [Match strategy, confidence, media ID]  [View] [Disable]

   ── Your Custom Namespaces ──
   archive:          [5 fields] [Edit] [Delete] [Preview]
   family:           [3 fields] [Edit] [Delete] [Preview]

   [Create New Namespace]
   ```
2. Click [Create New Namespace] → modal:
   ```
   NEW NAMESPACE

   Namespace Name:    [archive___________]  (alphanumeric, no spaces)
   Description:       [My archive metadata_____]

   FIELDS:
   [+] Add Field

   Name                Type              Default Value
   collection          text              [e.g., "Summer 2024"]
   source              select            [archive | personal | shared]
   tags                text (comma)      []

   [Create Namespace]  [Cancel]
   ```
3. When user exports, they can optionally set values for custom fields:
   - On Results page, show: "Apply archive metadata?" with prefilled values
   - Values are written to XMP sidecar files or EXIF (if supported)
4. Presets (Story 12 in pro roadmap) can save common namespace configurations for reuse

**Priority**: P3 (nice-to-have)
**Rationale**: Custom schemas are a power-user feature. They justify the Pro price for archivists and photo enthusiasts. Most free users won't use this, but Pro users who need it will love it and rarely churn.

---

## Story 19: Presets Should Save Time for Repeat Exports
**As a** Pro user who exports monthly from Snapchat
**I want to** save my upload preferences (EXIF embed, burn overlays, etc.) as a preset
**So that** I don't have to reconfigure every month

**Current state**: The Presets page (`/presets`) exists in navigation but has no functionality. Pro roadmap mentions this (Feature #12).

**Proposed fix**:
1. Presets page shows:
   ```
   EXPORT PRESETS

   Save common upload configurations to speed up monthly exports.

   ── Built-in Presets ──
   Photo Library Import    [Use] [Preview]
   Archival              [Use] [Preview]
   Social Media          [Use] [Preview]

   ── Your Custom Presets ──
   Monthly Snap Export   [Use] [Edit] [Delete] [Preview]

   [Create New Preset]
   ```
2. Click [Create New Preset] → modal:
   ```
   NEW PRESET

   Name:    [Monthly Snap Export________]

   PROCESSING OPTIONS:
   ☑ Add date/time text to photos
   ☑ Embed EXIF metadata
   ☐ Export chats in dark mode
   ☐ Generate XMP sidecars

   OPTIONAL: Advanced Settings
   ☐ Process only specific lanes (memories, stories, chats, etc.)
   ☐ GPS time window: [5___] minutes

   [Save Preset]  [Cancel]
   ```
3. On upload page, add a dropdown: "Quick Start: [Monthly Snap Export ▼]"
   - Clicking a preset auto-fills the upload form
   - User can override before uploading
4. Presets are specific to the user (not shared)

**Priority**: P2 (medium)
**Rationale**: Presets reduce friction for repeat users and increase monthly active usage. Users with good habits (monthly exports) are less likely to churn. Small convenience features drive retention.

---

## Story 20: Snapchat Deadline Banner Should Auto-Disable Post-Sept-30
**As a** product ops person
**I want to** ensure the Snapchat deadline banner doesn't stay up after the deadline passes
**So that** we don't look broken or out-of-touch after Sept 30, 2026

**Current state**: Story 6 proposes an urgent banner, but there's no mechanism to disable it after the deadline.

**Proposed fix**:
1. The deadline banner includes a config variable:
   ```python
   SNAPCHAT_DEADLINE = datetime(2026, 9, 30, 23, 59, 59)

   # In template:
   {% if now() < SNAPCHAT_DEADLINE %}
      <div class="deadline-banner">⚠️ DEADLINE: Snapchat's storage cap...</div>
   {% endif %}
   ```
2. After Sept 30, 2026, the banner automatically disappears
3. Post-deadline messaging pivots to: "Snapchat's storage cap is now live. Snatched is your permanent backup."
4. Create a manual flag in Settings > Environment Variables to override the banner display (for testing or emergency)

**Priority**: P3 (nice-to-have)
**Rationale**: Time-based messaging should be automated to prevent stale copy. Keeps the product feeling current and intentional.

---

## Summary

These 20 stories represent a comprehensive product strategy for Snatched v3 focused on:

- **Conversion**: Stories 1–3, 9, 16 (feature gating, pricing visibility, frictionless upgrades)
- **Retention**: Stories 5, 11, 15 (email reminders, feedback loops, re-engagement)
- **Urgency**: Story 6 (Snapchat deadline messaging)
- **Social Proof**: Story 10 (testimonials, usage stats)
- **Brand Consistency**: Story 14 (voice, visual identity, tone across every interaction)
- **Power User Features**: Stories 17–19 (Friends, Schemas, Presets)
- **UX Clarity**: Stories 7, 12 (onboarding, settings organization)
- **User Feedback**: Story 11 (review collection, testimonials)

**Key Themes:**
1. **Free → Pro conversion happens at aha moments** (download, quota limit, feature lock)
2. **Pricing should be visible everywhere**, not hidden behind clicks
3. **Locked features should tease, not block** (small cost to implement, huge impact on conversion)
4. **Email is powerful for retention and re-engagement** (time-based reminders, urgency, lifecycle)
5. **Brand voice matters**—every modal, toast, and error message reinforces or undermines the product
6. **Power tools are the Pro differentiator** (metadata editing, GPS correction, custom schemas)

---

**Next Steps**:
- Round 2: Gather feedback from Designer (Agent A) and Engineer (Agent B)
- Prioritize stories by effort + impact
- Implement P0 stories first (unlock conversion path)
- Measure conversion rate and churn metrics post-launch
