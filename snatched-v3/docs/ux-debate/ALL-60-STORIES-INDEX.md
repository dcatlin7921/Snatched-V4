# Snatched v3 UX Debate — All 60 Stories Index

**Purpose**: Single reference document for all stories across three agents
**Date**: 2026-02-24
**Format**: Organized by agent, with conflict/support annotations from Round 2

---

## Quick Navigation
- [Agent A: New User Advocate](#agent-a-new-user-advocate-23-stories) (20 from Round 1 baseline + 3 new)
- [Agent B: Power User Champion](#agent-b-power-user-champion-20-stories)
- [Agent C: Product Strategist](#agent-c-product-strategist-20-stories)
- [Conflicts By Theme](#conflicts-by-theme)
- [Consensus Picks (Top 15)](#consensus-picks-top-15-stories)

---

## Agent A: New User Advocate (23 Stories)

*Persona: Casual users, first-time Snapchat exporters, non-technical users, folks who just want to rescue memories*

### Round 1 Baseline (20 Stories) — Implicit
These were the baseline expectations from the debate setup:
1. Simple upload form (no confusing options)
2. Clear progress indication during processing
3. Celebratory success message on first download
4. Plain-language error messages
5. Obvious "Download" button (no treasure hunt)
6. Help/documentation visible and accessible
7. No hidden features that confuse new users
8. Confirmation before destructive actions
9. Responsive design (works on mobile)
10. Clear explanation of what each Results page section means
11. No unexplained jargon or technical terms
12. Guided tour or tips for first-time users
13. Privacy assurances upfront
14. Clear onboarding before upload
15. Visible next-step guidance (don't leave user wondering "now what?")
16. Tier information presented without pressure (not constant "upgrade" nags)
17. Email notifications for job completion (don't force app checking)
18. Mobile-friendly corrections workflow
19. Safe settings (don't accidentally delete data)
20. Supportive tone in all copy

### Round 2 New Stories (3)
1. **A1: Guided Results Page for First-Time Users**
   - **As a** new user viewing Results for the first time
   - **I want to** see a guided tour of what each section means (Matches | Assets | Chats | Stats)
   - **So that** I understand the data I recovered and feel confident downloading
   - **Status**: NEW, **Priority**: P1

2. **A2: Empty States & Progressive Education**
   - **As a** first-time user on an empty Dashboard
   - **I want to** see clear guidance on what to do next, not just blank space
   - **So that** I know my first action is to upload a Snapchat export
   - **Status**: NEW, **Priority**: P1

3. **A3: Error Recovery & Empathy**
   - **As a** user whose upload failed or job crashed
   - **I want to** see a clear explanation (in plain English, not error codes) + next steps
   - **So that** I don't feel helpless or abandoned
   - **Status**: NEW, **Priority**: P2

---

## Agent B: Power User Champion (20 Stories)

*Persona: Data hoarders, photographers, multi-account users, technical users demanding efficiency*

### Priority Breakdown

#### P0 (Critical)
1. **B-1: Dashboard as Command Center**
   - Stats badge, quick-action dropdown, progress bar on running jobs
   - **Status**: Supported by A (with "simplified" caveat), Supported by C
   - **A Note**: Show stats only on hover/toggle for new users

2. **B-2: Keyboard-First Navigation**
   - Global shortcuts (U, D, C, Ctrl+D, ?), help modal
   - **Status**: Supported by A with guardrails (opt-in for new users)
   - **A Note**: Hidden by default until second export

3. **B-5: One-Click Download from Dashboard**
   - Download button on card, overlay menu (ZIP | metadata | copy link)
   - **Status**: Universally supported
   - **Priority**: P0

#### P1 (High)
4. **B-3: Batch Operations Across Multiple Jobs**
   - Multi-select, sticky footer, Ctrl+A, filter bar
   - **Status**: Supported by A with condition (show when 3+ jobs)
   - **A Note**: Hide checkboxes on Dashboard until user has 3+ jobs

5. **B-6: Correction Workflow as Pipeline**
   - Wizard: GPS → Timestamps → Redact → Match Config, left sidebar steps
   - **Status**: Universally supported
   - **A Note**: Make optional, hide behind [Corrections] button

#### P2 (Medium)
6. **B-4: Upload Presets & Configuration Reuse**
   - Settings > Upload Presets, preset dropdown on upload
   - **Status**: Supported by A with deferral (first upload simple, second+ presets)
   - **A Note**: First upload: just 2 toggles (Add dates | Include chats)

7. **B-7: Job Groups for Bulk Upload Batches**
   - Group name, expanded/collapsed view, group stats, batch actions
   - **Status**: Neutral from A/C
   - **Priority**: P2, Pro/Team feature

8. **B-8: Advanced Match Configuration**
   - 6 strategy sliders, confidence threshold, preview, apply & reprocess
   - **Status**: Neutral from A/C
   - **Priority**: P2

9. **B-10: Data Density (Compact View)**
   - 100 rows/page, column customization, export CSV
   - **Status**: Supported by A with toggle (default 20 rows, opt-in to 100)
   - **A Note**: Hidden until second export

10. **B-12: Reprocess Selective Lanes or Phases**
    - Checkboxes for Ingest | Match | Enrich | Export, sub-options
    - **Status**: Neutral from A/C
    - **Priority**: P2

11. **B-13: Export Results in Multiple Formats**
    - JSON, CSV, PDF summary report
    - **Status**: Neutral from A/C
    - **Priority**: P3

12. **B-15: Smart Filtering and Saved Searches**
    - Filter bar (confidence, strategy, date, missing data), save searches
    - **Status**: Neutral from A/C
    - **Priority**: P2, high impact for power users

#### P3 (Nice-to-Have)
13. **B-9: API Keys and Automation Integration Visibility**
    - Quick-access card on Dashboard, webhook/schedule widgets
    - **Status**: C proposes hiding from free users (tier gating)
    - **Priority**: P3, Pro feature

14. **B-11: Rapid Job Status from Dashboard Polling**
    - Faster refresh intervals, desktop notifications, Jump to Job overlay
    - **Status**: Neutral from A/C
    - **Priority**: P3

15. **B-14: Correction History and Undo**
    - Timeline of corrections, view/undo buttons, Ctrl+Z shortcut
    - **Status**: Neutral from A/C
    - **Priority**: P3

16. **B-16: Multi-Format Asset Download and Preview**
    - Asset checkboxes, bulk select, download as ZIP, preview modal
    - **Status**: Neutral from A/C
    - **Priority**: P2

17. **B-17: Webhook Triggers and Scheduled Reprocessing**
    - Webhook URL/events form, schedules page, test button
    - **Status**: C proposes tier gating (Pro feature)
    - **Priority**: P2, Pro feature

18. **B-18: Tagging and Metadata Organization**
    - Tag system, category toggles (Person/Context/Year), Dashboard filter
    - **Status**: Neutral from A/C
    - **Priority**: P3

19. **B-19: Comparative Analysis Across Multiple Jobs**
    - /compare page, side-by-side view, merged table, stat comparison
    - **Status**: Neutral from A/C
    - **Priority**: P3

20. **B-20: Keyboard-Navigable Results Table**
    - Arrow keys, Ctrl+Home/End, Ctrl+G (go to row), /, I, Ctrl+C
    - **Status**: Neutral from A/C
    - **Priority**: P3

---

## Agent C: Product Strategist (20 Stories)

*Persona: Product team, conversion/retention focus, monetization, brand voice, user lifecycle*

### Priority Breakdown

#### P0 (Critical)
1. **C-1: First-Time User Sees the Pricing Gate**
   - Sticky card on download page: "Your memories expire in 30 days. Pro: 180 days. [Upgrade]"
   - **Status**: Supported by A with timing adjustment (show *after* download completes)
   - **A Note**: Gentle tone ("want more?"), not fear ("they'll expire")

2. **C-3: Locked Features Should Tease, Not Block**
   - Pro buttons: yellow outline + badge + hover tooltip + upgrade modal
   - **Status**: Supported by A with alternative (gray disable instead of yellow tease)
   - **A Note**: Show after 1-2 exports, not immediately

3. **C-9: Upgrade Flow Should Be Frictionless**
   - Modal overlay, Stripe checkout, immediate feature unlock, toast
   - **Status**: Universally supported
   - **Priority**: P0

#### P1 (High)
4. **C-2: Landing Page Pricing Section**
   - Pricing table (Free | Pro | Team | Unlimited) below How It Works
   - **Status**: Supported by A (after onboarding ships in Phase 2)
   - **Priority**: P1

5. **C-4: Tier Badge on Dashboard & Quota Page**
   - Dashboard tier card with upgrade button, quota page with warning
   - **Status**: Supported by A with relocation (move from Dashboard to Settings > Account)
   - **A Note**: Show quota bar on Dashboard instead

6. **C-6: Urgency Messaging (Snapchat Deadline)**
   - Top banner: "⚠️ DEADLINE: Sept 30, 2026..." with messaging adjustments
   - **Status**: Supported by A with tone adjustment (empowering, not scary)
   - **A Note**: Lead with "help," not "fear"

7. **C-12: Settings Page Separate Account from Danger Zone**
   - Clear sections: Preferences | Account | Danger Zone; 24h deletion delay
   - **Status**: Universally supported
   - **Priority**: P1

8. **C-13: API Keys & Webhooks Should Be Prominently Gated**
   - Visible only to Pro+, free users see upgrade gate
   - **Status**: Supported by A (part of progressive disclosure)
   - **Priority**: P1

9. **C-14: Brand Voice Should Be Consistent**
   - Audit all modals, toasts, errors for active voice, tone, visual identity
   - **Status**: Universally supported
   - **Priority**: P1

10. **C-16: Pro Features Should Be Visible in Navigation**
    - Friends, Schemas, Presets in nav (with Pro badges) for all users
    - **Status**: Supported by A with deferral (hide for new users, show for returning)
    - **A Note**: Progressive disclosure: new users see Upload | Dashboard | Settings only

#### P2 (Medium)
11. **C-5: Email Retention Reminder (Lifecycle)**
    - 7-day + 1-day before expiry, download link + upgrade CTA
    - **Status**: Supported by A (part of retention strategy)
    - **Priority**: P2

12. **C-7: Onboarding Flow Before Upload**
    - 4-card walkthrough: What | Safety | Tiers | Ready; skippable
    - **Status**: Universally supported
    - **Priority**: P1 (highest impact)

13. **C-8: Referral / Sharing Mechanic**
    - /referrals page, unique ref link, social proof cards on Results page
    - **Status**: Neutral from A/B
    - **Priority**: P2

14. **C-10: Social Proof on Landing Page**
    - Usage stats, testimonials, trust badges
    - **Status**: Neutral from A/B
    - **Priority**: P1 (for conversion)

15. **C-11: Feedback Loop (Post-Export)**
    - Star rating + review modal on Results page, email follow-up for 1-3 stars
    - **Status**: Neutral from A/B
    - **Priority**: P2

#### P3 (Nice-to-Have)
16. **C-15: Re-engagement Campaign for Churned Users**
    - Weekly Haiku job, email to users inactive 60+ days
    - **Status**: Neutral from A/B
    - **Priority**: P3

17. **C-17: Friends Page Should Leverage Snapchat Data**
    - Friend mappings (username → display name), auto-populate after export
    - **Status**: Neutral from A/B
    - **Priority**: P2, Pro feature

18. **C-18: Schemas Page Should Support Custom Metadata**
    - Custom XMP namespaces, field definitions, preview
    - **Status**: Neutral from A/B
    - **Priority**: P3, Pro feature

19. **C-19: Presets Should Save Time**
    - Save upload preferences (EXIF, overlays, etc.), preset dropdown on upload
    - **Status**: Overlap with B-4 (Agent C adds metadata/schema angle)
    - **Priority**: P2, Pro feature

20. **C-20: Snapchat Deadline Banner Auto-Disable**
    - Config variable, disappears after Sept 30, 2026
    - **Status**: Neutral from A/B (pure ops)
    - **Priority**: P3

---

## Conflicts By Theme

### 1. Feature Visibility (When to Show)
| Theme | Agent B | Agent C | Agent A | Consensus |
|-------|---------|---------|---------|-----------|
| **Keyboard shortcuts** | From day 1 | N/A | Opt-in after 2 exports | **A3: Opt-in, discoverable** |
| **Batch operations** | Always visible | N/A | Show when 3+ jobs | **A3: Conditional** |
| **Upload presets** | First upload | C-19 (Pro) | Second export+ | **A3: Simple first, presets later** |
| **Pro features in nav** | N/A | C-16 (all visible) | Progressive (hidden → revealed) | **A3: Progressive disclosure** |
| **Data density** | 100 rows default | N/A | 20 rows default | **A3: 20 default, 100 opt-in** |

### 2. Monetization Timing
| Tactic | Agent B | Agent C | Agent A | Consensus |
|--------|---------|---------|---------|-----------|
| **Pricing visibility** | N/A | C-1 (immediate) | After first success | **A3: After download, gentle tone** |
| **Feature teasing** | N/A | Yellow outline + tease | Gray disable + later | **A3: Gray disable, post-1st-export** |
| **Tier badge on Dashboard** | N/A | C-4 (prominent) | Settings only | **A3: Settings > Account** |
| **Upgrade pressure** | N/A | High urgency | Contextual, low pressure | **A3: Triggered by feature interest** |

### 3. New User Experience
| Aspect | Agent B | Agent C | Agent A | Consensus |
|--------|---------|---------|---------|-----------|
| **Onboarding** | N/A | C-7 (4 cards) | Mandatory, skippable | **Agreed: Mandatory + skippable** |
| **Empty state** | N/A | N/A | A2 (guidance) | **New story: A2** |
| **Results page guidance** | N/A | N/A | A1 (tour) | **New story: A1** |
| **Error messages** | N/A | N/A | A3 (empathy) | **New story: A3** |

### 4. Corrections Workflow
| Aspect | Agent B | Agent C | Consensus |
|--------|---------|---------|-----------|
| **Pipeline wizard** | B-6 (seamless) | N/A | **Agreed: Pipeline, optional** |
| **Visibility** | Always available | N/A | **Agreed: Hide behind [Corrections] button** |

---

## Consensus Picks (Top 15 Stories)

These 15 stories represent unanimous or near-unanimous agreement on implementation priority:

| Rank | Story | Agent | Phase | Why |
|------|-------|-------|-------|-----|
| 1 | C-7: Onboarding Flow | C | 1 | Critical path; prevents confusion |
| 2 | B-1: Dashboard (simplified) | B | 1 | Clean home for new users |
| 3 | B-5: One-click Download | B | 1 | Easiest path to files |
| 4 | C-1: Pricing Gate (timing-adjusted) | C | 1 | Monetization at right moment |
| 5 | B-6: Corrections Wizard (optional) | B | 1 | Reduces Results page intimidation |
| 6 | C-14: Brand Voice Audit | C | 1 | Consistency = trust |
| 7 | C-12: Settings Separation | C | 1 | Safety (no accidental deletion) |
| 8 | B-2: Keyboard Shortcuts (opt-in) | B | 2 | Power user efficiency, safe |
| 9 | B-3: Batch Operations (conditional) | B | 2 | Scale support, hidden until relevant |
| 10 | B-4: Upload Presets (deferred) | B | 2 | Repeat user convenience |
| 11 | C-3: Pro Feature Teasing (refined) | C | 2 | Conversion, gentle timing |
| 12 | C-2: Landing Page Pricing | C | 2 | Pre-commit transparency |
| 13 | C-9: Frictionless Upgrade | C | 3 | Conversion flow <60s |
| 14 | B-15: Filtering & Saved Searches | B | 3 | Power user feature discovery |
| 15 | C-5: Email Retention | C | 3 | Churn reduction |

**New Stories (Not in Top 15, but Important)**:
- **A1: Guided Results Tour** — Phase 1, improves new user understanding
- **A2: Empty States** — Phase 1, prevents user confusion
- **A3: Error Recovery** — Phase 1, builds empathy and support

---

## Stories with Deferred/Conditional Implementation

These stories are valuable but should be hidden or gated until conditions are met:

| Story | Condition | When Available |
|-------|-----------|-----------------|
| B-2 (Keyboard Shortcuts) | User completes 2+ exports | After 2nd export |
| B-3 (Batch Operations) | User has 3+ jobs on Dashboard | When 3+ jobs visible |
| B-4 (Upload Presets) | User on 2nd+ upload | 2nd upload onward |
| B-10 (Data Density/Compact) | User has 100+ results | Opt-in toggle |
| C-3 (Pro Teasing) | User completes 1-2 exports | After 1-2 exports |
| C-16 (Pro Nav Features) | User is returning/power user | After 2+ exports or visible to Pro users |

---

## Stories Not in Top 15 (But Still Valuable)

These 45 stories should be prioritized in Phase 2-3 based on team capacity and user feedback:

**Strongly Supported** (B's power user features):
- B-7 (Job Groups)
- B-8 (Advanced Match Config)
- B-12 (Selective Reprocessing)
- B-13 (Export Formats)
- B-16 (Asset Preview & Download)
- B-17 (Webhooks)
- B-18 (Tagging)
- B-19 (Comparative Analysis)
- B-20 (Keyboard Table Nav)

**Pro/Advanced Features** (C's monetization support):
- C-8 (Referrals)
- C-10 (Social Proof)
- C-11 (Feedback Loop)
- C-13 (API Key Gating)
- C-15 (Re-engagement)
- C-17 (Friends Page)
- C-18 (Schemas)
- C-19 (Presets for Pro)
- C-20 (Banner Auto-disable)

**Nice-to-Have Power User** (B's efficiency):
- B-9 (API Visibility)
- B-11 (Job Status Polling)
- B-14 (Correction History)

---

## Implementation Dependencies

**Phase 1 Blockers** (must do first):
1. C-7 (Onboarding) — blocks launch readiness
2. B-5 (Download button) — blocks core workflow
3. Database schema updates for features (job metadata, user preferences)

**Phase 2 Blockers** (after Phase 1):
1. B-2, B-3, B-4 (keyboard, batch, presets) — requires UI component system
2. C-3, C-9 (pricing, upgrade flow) — requires Stripe integration + feature gating backend

**Phase 3 Blockers** (after Phase 2):
1. B-15 (filtering) — requires search API
2. C-5 (email retention) — requires email service + cron job

---

## Questions Remaining for Consensus

1. **Onboarding Completeness**: Should onboarding cover tier system (Free/Pro) or save that for later landing page?
2. **Pro Feature Visibility**: Should Pro-only features be completely hidden from nav for free users, or always visible (with lock icon)?
3. **Error Tone**: Should errors use brand voice "mission aborted" metaphor, or plain English "Something went wrong"?
4. **Keyboard Discovery**: Show keyboard tips proactively (toast on first action), or only in `?` help modal?
5. **Mobile Batch Operations**: Should batch operations be hidden on mobile, or nested in menu?

---

**Status**: Draft index for consensus discussion
**Last Updated**: 2026-02-24
**Owner**: Agent A (New User Advocate)
