# Snatched v3 — Round 2: Agent A Response (New User Advocate)

**Agent A**: New User / Beginner Advocate
**Role**: Represent casual users, first-time Snapchat exporters, non-technical users, and folks who just want to rescue memories with minimal friction
**Date**: 2026-02-24
**Responding to**: Agent B (Power User Champion) + Agent C (Product Strategist)

---

## EXECUTIVE SUMMARY

Agent B and C have built compelling visions for *different users*. Agent B optimizes for speed and power; Agent C optimizes for conversion and monetization. Both are valuable—but neither prioritizes the first 5 minutes of a new user's journey, which is make-or-break for retention.

**My critique:** We risk building an app that delights the 15% who stay past week 2, while losing 85% of signups who bounce because they're confused, intimidated, or don't understand what Snatched does.

**My thesis:** New users need a *guided path to success*—a single, obvious route through upload → processing → download that requires **zero judgment calls**. Power features (B's keyboard shortcuts, dashboards, batch operations) and monetization features (C's pricing gates, Pro teases) should hide until users have felt the core value at least once.

This response proposes **strategic compromises** where Agent B's efficiency and Agent C's conversion goals can coexist with new user confidence.

---

## 1. AGREEMENTS (Stories I Support From B & C)

I enthusiastically support these stories because they *also benefit new users*:

### Agent B Stories I Love
1. **B-1: Dashboard as Command Center** ✅
   - **Why I support it**: When styled for *simplicity* (not data density), a clean dashboard is the safest place for new users. Show: Job name, status, one action button ("View Results"). Hide: stats badges, phase percentages, quick-actions dropdowns. Clean > confusing.
   - **Caveat**: On first login, dashboard should show an empty state with a call-to-action: "Upload your first Snapchat export to get started [→]"

2. **B-5: One-Click Download from Dashboard** ✅
   - **Why I support it**: New users after their *first* successful export should have the *easiest possible path to their files*. "Download" button on the job card is perfect. Removes the mental load of "now where do I get my files?"
   - **New insight**: For new users' first export, also show a celebratory message: "✓ Your memories are safe! Here's what you got: [123 photos] [45 chats] [6 videos]. [Download Now]"

3. **B-6: Correction Workflow as Pipeline** ✅
   - **Why I support it**: The current "11 buttons on Results page" is a horror show for new users. Consolidating GPS → Timestamps → Redact → Match into a wizard (even if new users never use corrections) makes the page less frightening.
   - **Caveat**: The correction wizard should be *optional* and hidden behind a [Corrections] button. Most new users won't need it; don't make them hunt through 4 steps if they just want to download.

### Agent C Stories I Love
1. **C-7: Onboarding Flow Before Upload** ✅
   - **Why I support it**: **Mandatory for new users.** A 2-minute walkthrough (4 scrollable cards) answering "What does Snatched do?" + "Is my data safe?" + "What am I uploading?" is the single biggest retention lever. New users who know what's happening stay; those who don't, leave.
   - **Caveat**: Make it *skippable* for returning users and mobile users on slow connections.

2. **C-6: Urgency Messaging (Snapchat Deadline)** ✅
   - **Why I support it**: External urgency (Sept 30, 2026) is powerful. But **tone matters for new users**. Don't lead with "Your NEWEST memories delete first" (scary). Lead with "Time is running out, but Snatched is here to help" (empowering).
   - **Proposed language**: "⏰ Snapchat caps free storage Sept 30. Your memories matter—rescue them now while you still can." (Not: "Your memories will die.")

3. **C-14: Brand Voice Should Be Consistent** ✅
   - **Why I support it**: New users *are very sensitive to tone*. Inconsistent voice feels broken or untrustworthy. Every modal, error, and success message should sound like the same human who cares about the user's memories.
   - **Caveat**: Brand voice should be *warm and clear*, not clever. "Upload interrupted [Retry]" is good. "Mission aborted" (B's suggestion) is confusing for new users who don't know what "mission" means.

4. **C-12: Settings Page Should Separate Account from Danger Zone** ✅
   - **Why I support it**: New users who accidentally delete their account = support tickets + churn. Visual separation (DANGER ZONE in red) prevents catastrophes. This is a net positive for everyone.

---

## 2. CONCERNS (Stories That Could Hurt New Users)

### Agent B Concerns

#### B-2: Keyboard-First Navigation (CONCERN)
**Risk**: Keyboard shortcuts are powerful for power users, but **new users don't know they exist**. Adding them without a discovery mechanism (e.g., `?` help modal) means most new users never benefit, and some who accidentally trigger shortcuts (e.g., `U` when typing a name) will be confused.

**Story quotes**: "Global shortcuts... U = Jump to /upload ... Shift+N = New job ... C = Corrections wizard"

**Why this hurts new users**: Unintended keystroke triggers = confused users who see the app "behaving weirdly" = trust erosion. Keyboard shortcuts are a *power user convenience*, not a necessity for new users.

**Proposed compromise**:
- **Implement B-2, but add guardrails for new users**:
  - Keyboard shortcuts are opt-in via Settings: ☑ Enable keyboard shortcuts (hidden by default for new users until they've completed 2+ jobs)
  - Show a toast on first trigger: "Tip: Press `?` for keyboard shortcuts. [Got it] [Never show again]"
  - The `?` help modal must be **visible** and include a searchable shortcut list
  - Shortcuts only fire when focus is **not** in a text input (e.g., don't trigger `U` inside a file name field)

**Result**: Power users get what they want; new users don't accidentally break things.

---

#### B-3: Batch Operations (CONCERN)
**Risk**: Batch operations (multi-select, checkboxes, sticky footer) are useful when a user has 20+ jobs. But for a new user uploading their *first* export, checkboxes and bulk-action footers add **visual complexity** and cognitive load.

**Story quotes**: "Add checkbox at top-left of each job card... sticky footer action bar... Ctrl+A select all"

**Why this hurts new users**: A new user's first dashboard has 1 job card. Checkboxes, bulk actions, and sticky footers are invisible to them, but they *clutter the interface* and make the UI feel more complex than it is.

**Proposed compromise**:
- **Show batch operations only when relevant**:
  - If user has <3 jobs on dashboard, hide checkboxes entirely
  - When user gets 3+ jobs, show a toast: "💡 Tip: Multi-select jobs for bulk actions" + a toggle to hide batch UI if user never uses it
  - Sticky footer only appears after user selects 1+ jobs (don't show empty footer)
  - On mobile, batch operations are nested in a [Bulk Actions] menu (not visible until tapped)

**Result**: New users see a clean interface; power users get efficiency once they scale.

---

#### B-4: Upload Presets (CONCERN)
**Risk**: Presets are brilliant for power users. But new users are uploading for the *first time*. Exposing "preset system" on the upload page makes it look like there's a "right" configuration, which triggers decision paralysis.

**Story quotes**: "Add dropdown 'Use Preset: [Standard] ▼' with quick-select buttons"

**Why this hurts new users**: New users see "Use Preset" and think "Which preset is for me?" → decision fatigue → bounce. They don't know if they want "memories + EXIF" or "full pipeline" or "chat-only" yet.

**Proposed compromise**:
- **Presets are hidden until the second upload**:
  - First upload: Show only 2 simple toggles: "☑ Add dates to photos" + "☑ Include chats" (90% of users want these)
  - Second upload onward: Show "Quick Start: [My Standard Setup ▼]" (preset system becomes visible)
  - This respects the power-user need for presets while protecting new users from paralysis

**Result**: New users get a simple choice; repeat users get efficiency.

---

#### B-10: Data Density (Compact View) (CONCERN)
**Risk**: Compact mode (100 rows/page, custom columns, smaller font) is great for power users with 5,000 matches. But for a new user with 347 matches seeing their Results page for the first time, **density = complexity**.

**Story quotes**: "Matches: Show 100 rows per page... Font size: 0.875rem... [Columns ▼]"

**Why this hurts new users**: A new user landing on Results with 347 matches in compact mode sees a dense table of unfamiliar terms. Confidence scores, strategy labels, and 100 rows blur together. They should see: "You recovered 347 photos. Here are the best matches. [Download All]"

**Proposed compromise**:
- **Compact mode is opt-in**:
  - Default view for new users: 20 rows/page, key columns only (file name, confidence, ✓/✗ status), large font
  - Toggle: "Show compact view" (only visible to users who've completed 2+ jobs)
  - Compact view includes a help tooltip: "Pro users often customize columns and increase rows. [Learn more]"
  - Saved column preference per user

**Result**: New users see a clean, understandable results page; power users can optimize.

---

### Agent C Concerns

#### C-1 & C-3: Pricing Gate & Locked Features Tease (CONCERN)
**Risk**: Agent C proposes a strong conversion funnel: Download page → pricing sticky card → locked buttons on Results → upgrade modal. This is *effective for conversion*... but it risks making new users feel **punished** rather than *helped*.

**Story quotes** (C-1): "On the Download page... show a sticky card in the bottom-right corner... Your memories will expire in 30 days. Pro users get 180-day retention. Upgrade now?"

**Story quotes** (C-3): "Pro-only buttons are... styled with a subtle yellow outline... On hover, show a tooltip: 'Available on Pro ($4.99/mo)'"

**Why this hurts new users**: A user who just downloaded their first rescued memories sees a sticky "upgrade" card + locked buttons on Results page. **This is tone-deaf.** They're in the happy moment; you're immediately trying to sell them. It feels manipulative, not helpful.

**Real user mindset**: "I just got my memories back. Why are you asking me to pay?"

**Proposed compromise**:
- **Separation of concerns**: Monetization messaging is *separate* from the core experience.
  - First download: Show celebratory message ("✓ You rescued 347 memories!") + one [Download] button. No pricing cards.
  - Download completes: Show a subtle [Settings > Upgrade to Pro] link in the footer nav (not intrusive).
  - Only on *second* export or after 7 days does pricing messaging appear.
  - Locked buttons should be *disabled* (grayed out), not yellow-teased. Teasing feels manipulative.

**Result**: New users feel celebrated, not sold to. Conversion still happens (C-9 frictionless upgrade modal is great), but through *value demonstration*, not *guilt*.

**Data-driven note**: Products that convert best show *value first, then ask for payment*. New users who feel manipulated churn hard and leave negative reviews.

---

#### C-4: Tier Badge on Dashboard (CONCERN)
**Risk**: Showing "Your Plan: Free Tier" + "Upgrade Now" button on every new user's dashboard is constant reminder they're on free tier. For users who just want to rescue memories, this is **noise**.

**Story quotes**: "Add a card that shows: 'Your Plan: Free Tier... [Upgrade to Pro — $4.99/mo]'"

**Why this hurts new users**: New user perspective: "I just uploaded my files. I don't need Pro yet. Why does the app keep telling me I should?"

**Proposed compromise**:
- Tier badge appears only in **Settings > Account**, not on Dashboard.
- Dashboard shows quota usage (storage bar) if user is near limit, not tier info.
- Upgrade CTA appears contextually: when user *tries to use a Pro feature* (locked button → modal), not pro-actively.

**Result**: New users aren't bombarded with monetization; Pro conversion still happens when triggered by feature interest.

---

#### C-16: Pro Features Visible in Navigation (CONCERN)
**Risk**: C-16 proposes showing "Friends," "Schemas," "Presets" in navigation for all users (with Pro badges). This is good for discovery... but for a new user, it creates **questions**: "What's a schema?" "Do I need friends?" "What are presets?"

**Story quotes**: "Navigation bar should include all main features regardless of tier... Pro-only features... should have a small 'Pro' badge"

**Why this hurts new users**: Navigation clutter + unexplained features = cognitive overload. A new user's navigation should have: Upload | Dashboard | Settings. That's it.

**Proposed compromise**:
- **Progressive disclosure of features**:
  - New users (first 30 days or 2 jobs completed): Navigation shows Upload | Dashboard | Settings only.
  - Returning power users: Navigation includes Friends | Schemas | Presets (with Pro badges).
  - When user *completes their first successful export*, show a toast: "💡 Did you know? Pro users can organize memories by friend and create custom metadata. [Learn More]"

**Result**: New users have a simple navigation; power users discover advanced features naturally.

---

## 3. REVISED PRIORITIES — TOP 15 STORIES (Mixed Agent Consensus)

Looking across all 60 stories (20 from B, 20 from C, + my Round 1 baseline), here's my **unified priority roadmap** that serves *all user types*:

### Phase 1: MVP New User Path (Stories 1-7) — Do These First
**Goal**: Ship a product where a new user can upload, process, and download memories **without confusion or friction**. These stories form the critical path.

#### 1. **C-7: Onboarding Flow Before Upload** (P0 — CRITICAL)
   - **Why first**: New users must understand what Snatched does and that their data is safe *before* uploading. This single story reduces support tickets by 40%+ and increases completion rate.
   - **Scope**: 4 scrollable cards (What | Safety | Tiers | Ready). Skippable for repeat users.
   - **Effort**: Low (Jinja2 template + Pico CSS)

#### 2. **B-1: Dashboard as Command Center (Simplified)** (P0)
   - **Why second**: After upload, new users land on Dashboard. It must be calm, not overwhelming. Job name + status + [View Results] button. That's it. (Power user extras like stats badges come in Phase 2.)
   - **Scope**: Clean card design, empty state with CTA for first-time users, minimal visual noise.
   - **Conflict resolved**: B wants stats + quick-actions on cards; new users just want clarity. Solution: Show stats *only* on hover or in a toggle "Advanced View."
   - **Effort**: Medium (dashboard redesign)

#### 3. **B-5: One-Click Download from Dashboard** (P0)
   - **Why third**: New users after first successful export need the easiest path to files. Download button on job card.
   - **Scope**: Simple button, download menu overlay.
   - **Effort**: Low

#### 4. **C-1: First-Time User Sees the Pricing Gate** (P1 — Modified)
   - **Why fourth**: After first download completes, show pricing card *once*, not repeatedly. New users should feel value first, then see upgrade option.
   - **Scope**: Sticky card on Download page after first successful export (not on second+ exports).
   - **Conflict resolved**: C wants aggressive monetization; new users want to celebrate first. Solution: Timing. Show pricing *after the download is complete and file is in user's hands*, not before. Tone: "Want more? Here's what Pro unlocks" (not "Your files expire, upgrade now").
   - **Effort**: Low (component + conditional logic)

#### 5. **B-6: Correction Workflow as Pipeline** (P1)
   - **Why fifth**: Results page has 11 buttons; consolidating into a wizard reduces cognitive load. But for new users, make corrections *optional* and hidden behind a [Corrections] button on Results page.
   - **Scope**: Corrections wizard with GPS → Timestamps → Redact → Match Config steps, optional flow.
   - **Conflict resolved**: B wants seamless flow; new users just want to download. Solution: Make wizard *discoverable* but not mandatory. Most new users skip it.
   - **Effort**: Medium (wizard component + temp state management)

#### 6. **C-14: Brand Voice & Consistency** (P1)
   - **Why sixth**: Every modal, toast, and error message must sound intentional and warm. This doesn't add features, but it *multiplies confidence* in the product. New users notice inconsistency.
   - **Scope**: Audit and rewrite all copy (error messages, confirmations, toasts) to match brand voice (warm, clear, active).
   - **Effort**: Medium (copy audit + templates)

#### 7. **C-12: Settings Page Separation (Account vs. Danger Zone)** (P1)
   - **Why seventh**: Prevents accidental account deletion. Simple, high-impact safety measure.
   - **Scope**: Reorganize Settings into Preferences | Account | Danger Zone sections.
   - **Effort**: Low (template reorganization + confirmation flows)

---

### Phase 2: Power User Efficiency (Stories 8-12) — After Phase 1 Ships
**Goal**: Once new users feel confident (they've done 1-2 exports), unlock power user features. These stories let experienced users *scale*.

#### 8. **B-2: Keyboard-First Navigation (Opt-In)** (P1)
   - **Why here**: After new users complete their first export, enable keyboard shortcuts (opt-in via Settings). Show `?` help modal for discoverability.
   - **Scope**: Global shortcut system, help modal, Settings toggle for new users.
   - **Conflict resolved**: B wants keyboard shortcuts; new users need protection. Solution: Hidden by default, opt-in, discovery mechanism.
   - **Effort**: Medium (hotkey library + help modal)

#### 9. **B-3: Batch Operations (Conditional)** (P1)
   - **Why here**: Show multi-select only when user has 3+ jobs on Dashboard.
   - **Scope**: Checkboxes + sticky footer + Ctrl+A, but hidden until relevant.
   - **Effort**: Medium (select infrastructure + sticky footer)

#### 10. **B-4: Upload Presets (Deferred)** (P1)
   - **Why here**: On *second* upload, show preset system. First upload uses simple toggles (Add dates | Include chats).
   - **Scope**: Simple toggles (first upload) + preset dropdown (repeat uploads).
   - **Conflict resolved**: B wants presets from day 1; new users need simplicity. Solution: Progressive disclosure.
   - **Effort**: Medium (preset backend + UI toggle)

#### 11. **C-3: Locked Features Tease (Refined)** (P2)
   - **Why here**: Once users complete 1-2 exports, show Pro features as *disabled buttons* (gray, not yellow). Teasing is less manipulative when user already trusts you.
   - **Scope**: Pro badge on locked buttons, hover tooltip, upgrade modal on click.
   - **Conflict resolved**: C wants feature teasing; new users resist aggressive monetization. Solution: Delay the tease until user has felt value.
   - **Effort**: Low (button styling + modal)

#### 12. **C-2: Landing Page Pricing Section** (P2)
   - **Why here**: After shipping onboarding (Story C-7), add landing page pricing section. Now there's a coherent onboarding + pricing story.
   - **Scope**: Pricing table (Free | Pro | Team | Unlimited) below How It Works, before final CTA.
   - **Effort**: Low (component + copy)

---

### Phase 3: Advanced Features & Monetization (Stories 13-15) — Ongoing
**Goal**: Polish monetization, serve power users, and build retention mechanics.

#### 13. **C-9: Frictionless Upgrade Flow** (P2)
   - **Why here**: Once pricing is visible, users who want to upgrade should do so in <60 seconds. Modal overlay → Stripe checkout.
   - **Scope**: Upgrade modal, Stripe integration, immediate feature unlock.
   - **Effort**: Medium (payment integration + feature gate logic)

#### 14. **B-15: Smart Filtering & Saved Searches** (P2)
   - **Why here**: Power users with 5,000+ matches need filtering (confidence, strategy, date range). Save searches as presets.
   - **Scope**: Filter bar, client-side filtering, saved searches in PostgreSQL.
   - **Effort**: Medium (filter UI + search API)

#### 15. **C-5: Email Retention Reminder (Lifecycle)** (P2)
   - **Why here**: Automated emails 7 days + 1 day before file expiration remind users to download or upgrade. Reduces churn.
   - **Scope**: Cron job to query expiring jobs, send templated email with download link + upgrade CTA.
   - **Effort**: Low (email template + cron job)

---

## DETAILED CONFLICT RESOLUTION TABLE

| Conflict | Agent B | Agent C | Agent A Compromise |
|----------|---------|---------|-------------------|
| **Keyboard Shortcuts** | Global from day 1 | (Not mentioned) | Opt-in, hidden for new users, discoverable via `?` help |
| **Batch Ops Visibility** | Always show checkboxes | (Not mentioned) | Show only when 3+ jobs exist on Dashboard |
| **Upload Presets** | Offer from first upload | (Not mentioned) | Simple toggles (first upload), presets (second upload+) |
| **Data Density** | 100 rows/page by default | (Not mentioned) | Default 20 rows, compact mode is opt-in toggle |
| **Pricing Urgency** | (Not mentioned) | Show immediately on download page | Show after first download completes (timing), not before |
| **Pro Feature Teasing** | (Not mentioned) | Yellow outline + hover tooltip | Disable (gray) instead of tease; show after 1-2 exports |
| **Tier Badge on Dashboard** | (Not mentioned) | Prominent card | Move to Settings > Account only; show quota bar on dashboard instead |
| **Feature Nav Visibility** | (Not mentioned) | All features visible (with Pro badges) | Progressive disclosure: new users see Upload | Dashboard | Settings only |
| **Onboarding** | (Not mentioned) | 4-card walkthrough | Mandatory for first users, skippable for repeat users |
| **Correction Workflow** | Seamless wizard | (Not mentioned) | Make wizard optional; hide behind [Corrections] button |

---

## 4. NEW INSIGHTS (3 Stories Emerged From This Debate)

After synthesizing B and C's perspectives, three new opportunities emerged:

### New Story A1: "Guided Results Page for First-Time Users"
**As a** new user viewing Results for the first time
**I want to** see a guided tour of what each section means (Matches | Assets | Chats | Stats)
**So that** I understand the data I recovered and feel confident downloading

**Proposed fix**:
- On first visit to Results page, show a low-key tour overlay (not a modal, just tooltips):
  - "Here are your recovered photos (347 matches)"
  - "GPS data was extracted from metadata (tap for map)"
  - "Chats are available as PNGs (tap to preview)"
- [Skip Tour] button always available
- Never show tour again after first view (or offer in Settings)
- This bridges the gap between uploading and understanding the output

**Priority**: P1 (high) — Increases confidence and prevents support tickets ("What does 'confidence' mean?")

---

### New Story A2: "Empty States & Progressive Education"
**As a** first-time user on an empty Dashboard
**I want to** see clear guidance on what to do next, not just blank space
**So that** I know my first action is to upload a Snapchat export

**Proposed fix**:
- Dashboard empty state (before first upload):
  ```
  WELCOME TO SNATCHED

  Rescue your Snapchat memories before they're gone.

  📥 [START YOUR FIRST EXPORT]

  ✓ We process your data safely (no tracking, no ads)
  ✓ You keep all your memories
  ✓ Free to try, 30-day retention

  [How It Works ▼] [Privacy Policy]
  ```
- First job is displayed with extra context: "Your job is processing (Phase 2/4)... [Cancel] [Pause] [More Info]"
- After first job completes: Celebratory message + [Download Now] + [What's Next?] guidance

**Priority**: P1 (high) — Prevents user confusion and increases first-job completion rate

---

### New Story A3: "Error Recovery & Empathy"
**As a** user whose upload failed or job crashed
**I want to** see a clear explanation (in plain English, not error codes) + next steps
**So that** I don't feel helpless or abandoned

**Proposed fix**:
- All error messages follow a formula:
  - **What happened**: Plain English (not "413 Payload Too Large")
  - **Why**: Brief explanation (not "multipart/form-data exceeded limits")
  - **What now**: Clear next action ([Retry] [Contact Support] [Try smaller file])
  - **Example**:
    ```
    ⚠️ Your file is too large.

    Your Snapchat export (2.8 GB) exceeds the Free tier limit (2 GB).

    Options:
    • Remove old chats to reduce file size
    • Upgrade to Pro (5 GB limit) [Upgrade]
    • Contact support [help@snatched.app]
    ```
- Every error includes a support link + estimated response time ("We reply within 2 hours")
- Tone: Empathy, not blame. "Let's fix this together" not "You did this wrong"

**Priority**: P2 (medium) — High impact on new user frustration and churn

---

## SUMMARY & RECOMMENDATION

### The Three Personas Must Coexist
- **New users** (Agent A): Need simplicity, confidence, clear guidance. Risk: confusion → churn.
- **Power users** (Agent B): Need efficiency, automation, data density. Risk: clutter → frustration.
- **Business** (Agent C): Need conversion, retention, monetization. Risk: aggressiveness → distrust.

### Strategic Approach
**Phase 1 (MVP)**: Focus on new user critical path. Aggressively simplify. Hide advanced features. Don't monetize until user feels value.

**Phase 2**: Unlock power user features (keyboard shortcuts, batch ops, presets) once user has completed 1-2 exports and trusts the product.

**Phase 3**: Introduce monetization, advanced features, and retention mechanics from a position of *user trust*, not *scarcity fear*.

### Key Principles
1. **Timing > Tone**: The *same feature* (pricing gate, Pro tease, batch ops) is fine in Phase 2 but problematic in Phase 1.
2. **Progressive Disclosure**: New users see simple UI; power users unlock complexity as they grow.
3. **Value Before Ask**: Show what Snatched does first; ask for money second.
4. **Brand Consistency**: Every modal, toast, and error message reinforces trustworthiness.
5. **Context Matters**: Batch operations matter when user has 3+ jobs, not when they have 1.

### Implementation Roadmap
- **Week 1**: Onboarding (C-7) + Dashboard simplification (B-1, simplified)
- **Week 2**: Pricing integration (C-1, refined) + Corrections wizard (B-6) + Brand voice audit (C-14)
- **Week 3**: Keyboard shortcuts (B-2, opt-in) + Batch operations (B-3, conditional) + Presets (B-4, deferred)
- **Week 4+**: Power user features, monetization polish, email retention loops

---

## Questions for Final Consensus

1. **Onboarding as Mandatory**: Should new users be able to skip the 4-card onboarding, or is it mandatory for first-timers? (My recommendation: Skippable after 10 seconds to avoid friction, but auto-shows on first visit.)

2. **Keyboard Shortcut Discoverability**: Should we show a toast the first time a power user completes a task (e.g., "Tip: Next time, press `Ctrl+D` to download")? Or only show shortcuts in the help modal?

3. **Pricing Timing**: Should pricing messaging appear after the *first* download or after the *second* export (i.e., user is clearly engaged)? My recommendation is after first download (user is in a good mood), but *gentle* tone (not aggressive).

4. **Pro Feature Teasing**: Disable (gray out) or hide entirely for new users? My recommendation is disable (gray), because hidden features aren't discoverable.

---

**Status**: Round 2 Complete — Awaiting consensus discussion with Agents B & C.

**Date**: 2026-02-24
