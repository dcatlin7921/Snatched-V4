# Snatched v3 — Final Consolidated UX Stories

**Version**: 1.0
**Date**: 2026-02-24
**Status**: Consensus Approved
**Owner**: Product Team

---

## 1. EXECUTIVE SUMMARY

This document consolidates 60+ user stories from three-agent UX debate (Agents A, B, C) into a single source of truth for Snatched v3 implementation. It reflects consensus decisions reached in Round 2 debate and represents the complete feature roadmap across 3 phases (MVP, Power Features, Retention).

**Core Design Principle**: Progressive Disclosure + Value Before Ask. New users see simplicity; power users unlock complexity. Users feel value first (rescued memories), then monetization messaging. Honest visual treatment; contextual rather than constant pressure.

**Audience**: Designers, engineers, product managers. Each story is actionable with specific implementation notes and route paths.

---

## 2. DESIGN PRINCIPLES (5 Consensus Rules)

1. **Progressive Disclosure** — Features appear as user capability increases, not all at once. New users see Upload | Dashboard | Settings. Power users (2+ exports) see advanced options. Reduces cognitive overload.

2. **Value Before Ask** — Monetization messaging comes *after* user rescues memories, not before. User completes download; *then* gentle "want more?" pricing card. Timing > tone.

3. **Timing > Tone** — Same feature OK in Phase 2 but problematic in Phase 1. Keyboard shortcuts, batch ops, Pro badges all become tools instead of clutter when introduced at the right moment.

4. **Gray Disable > Yellow Tease** — Pro-locked features shown gray + honest tooltip ("Available on Pro — Upgrade") rather than yellow outline + manipulative copy. Users see what's possible without suspicion of dark patterns.

5. **Clear Errors > Clever Copy** — Error messages prioritize clarity (plain English + next action) over brand voice jargon. "Upload interrupted. [Retry] or [Contact Support]" > "Mission aborted."

---

## 3. USER PERSONAS (3 Types)

**New User (First 30 days / <2 exports)**
- Arrived from Snapchat, wants to rescue memories quickly
- Non-technical, skittish about features/jargon
- Confused by options; prefers guided hand-holding
- Measures success: "Did I get my photos back?"
- Leaves if: unclear next steps, too many buttons, feature complexity

**Power User (2+ exports / Team/Technical)**
- Runs dozens of jobs, optimizes matches, batch-processes exports
- Wants efficiency: keyboard shortcuts, batch ops, presets
- Comfortable with advanced options; frustrated by simplified UX
- Measures success: time-to-completion, batch throughput
- Leaves if: slow UI, missing efficiency tools, "dumbed-down" defaults

**Product/Business (Conversion/Retention Focus)**
- Monetization, churn prevention, brand voice consistency
- Lifetime value, upgrade rates, retention metrics
- Feature gating, transparent tiering, email campaigns
- Measures success: Free→Pro conversion 8-12%, 30-day retention >60%

---

## 4. NAVIGATION ARCHITECTURE

### New Users (First 30 Days / <2 Exports)
```
SNATCHED | Upload | Dashboard | Settings
```
- Clean, minimal
- No pro-feature nav items
- Mobile: hamburger menu (standard 3-bar)

### Returning Users (2+ Exports / Team/Pro)
```
SNATCHED | Upload | Dashboard | [More ▼]
  ├─ Friends [PRO]
  ├─ Schemas [PRO]
  ├─ Presets [PRO]
  ├─ Webhooks [PRO]
  └─ Export
Settings | Quota
```
- [More ▼] menu appears after 2nd export
- Pro features marked with [PRO] badge
- Pro users see all items unlocked

### Mobile (All Users)
```
≡ MENU
├─ SNATCHED
├─ Upload
├─ Dashboard
├─ Settings
└─ More [→]
    ├─ Friends [PRO]
    ├─ Schemas [PRO]
    ├─ Presets
    ├─ Webhooks [PRO]
    └─ Export
```

**Badge placement**: Visible only when feature appears in nav (Phase 2+). Hover tooltip: "Available on Pro — Upgrade".

---

## 5. TOP 20 PRIORITIZED USER STORIES

### PHASE 1: Core Experience (Weeks 1-3)
Goal: New user can upload, process, download without confusion. First-export completion rate >85%.

---

#### Phase1.1: Onboarding Walkthrough
**Source**: C-7 | **Priority**: P0 | **Effort**: Medium

**As a** first-time user visiting the app
**I want to** see a 4-card onboarding walkthrough (What | Why Safe | Tiers | Ready)
**So that** I understand what Snatched does before uploading

**Implementation**:
- `/onboarding` modal: 4 full-width cards, thumb-friendly buttons
- Cards: "What is Snatched?" → "Your data stays private" → "Free & Pro tiers" → "[Let's go]"
- Trigger: `user.jobs.count == 0` (first visit check)
- [Skip] button always visible; auto-skip after 10 seconds (mobile)
- Remembered in `user_preferences.onboarding_seen` (don't show again)
- Single-column layout (mobile), desktop centered card

---

#### Phase1.2: Dashboard Simplified for New Users
**Source**: B-1 (simplified) | **Priority**: P0 | **Effort**: Low

**As a** new user on my home page
**I want to** see a clean dashboard: "Upload Export" big button, progress on current jobs, recent export list
**So that** I know my next action and can track progress

**Implementation**:
- Route: `/dashboard`
- Layout: CTA [Upload Export] (hero button) → Running Jobs (simple cards) → Recent Jobs (20 rows default)
- Cards show: filename, status, % complete, date
- No stats badges for new users (hidden via `user.exports.count < 2` check)
- Stats toggle: appears after 2nd export (Settings > Dashboard Preferences)
- Desktop: 2-column (CTA + running jobs left, recent right). Mobile: single-column

---

#### Phase1.3: One-Click Download
**Source**: B-5 | **Priority**: P0 | **Effort**: Low

**As a** user who just got results
**I want to** download ZIP with one click from Dashboard or Results page
**So that** I don't hunt for a button buried in modals

**Implementation**:
- Route: `/dashboard` card overlay + `/results/{job_id}` sticky header
- Button: [Download ZIP] in sticky header (always visible, top-right)
- Click behavior: download to browser default folder, show success toast
- Optional: overlay menu on long-press/click: "ZIP | Metadata JSON | Copy Link"
- Mobile: single [Download] button; menu accessible via [⋯] icon

---

#### Phase1.4: Progress Labels & Phase Clarity
**Source**: A-7 | **Priority**: P0 | **Effort**: Low

**As a** user with a running job
**I want to** see what phase the job is in (Ingest 45% | Match 0% | Enrich 0%)
**So that** I know it's not stuck and understand the timeline

**Implementation**:
- Job card shows: status badge + phase breakdown (horizontal progress bar)
- Phases: Ingest | Match | Enrich | Export (color-coded)
- Backend: emit phase + progress in SSE events
- Frontend: parse `event.data.phase` and `event.data.progress_pct`
- Dashboard + Results page sticky header both show this
- Tooltip on phase: "Ingest: extract memories. Match: find duplicates. Enrich: add metadata. Export: create ZIP."

---

#### Phase1.5: Post-Upload Feedback & Validation
**Source**: A-4 | **Priority**: P0 | **Effort**: Medium

**As a** user uploading a large Snapchat export
**I want to** see real-time feedback (% uploaded, ETA, "looks good" validation)
**So that** I feel confident the upload won't silently fail

**Implementation**:
- Route: `/upload`
- Drag-and-drop zone: visual feedback (border highlight, checkmark on valid ZIP)
- Progress: "Uploading... 45 MB / 120 MB (37%)"
- Validation: Check ZIP header, Snapchat JSON structure before upload
- Error toast: "Not a Snapchat export. [Try again] [Help]"
- Success toast: "Uploaded! Processing starts now... [View Job]"
- Mobile: tap-to-upload fallback (click zone, file picker)

---

#### Phase1.6: Empty State Guidance
**Source**: A-2 | **Priority**: P1 | **Effort**: Low

**As a** first-time user looking at empty Dashboard
**I want to** see clear text + CTA (not blank space) explaining what to do
**So that** I immediately know to upload a Snapchat export

**Implementation**:
- Route: `/dashboard` (first visit, zero jobs)
- Content: "No exports yet. Start by uploading your Snapchat data."
- CTA: Big [Upload Your First Export] button
- Illustration: Simple graphic (phone → cloud → zip)
- Mobile: single-column, thumb-friendly button
- Hidden once user has 1+ job

---

#### Phase1.7: Error Recovery with Empathy
**Source**: A-3 | **Priority**: P1 | **Effort**: Medium

**As a** user whose upload failed
**I want to** see plain English explanation + next steps
**So that** I don't feel helpless or abandoned

**Implementation**:
- Error template: [⚠️ icon] Problem + Reason + Next Action
- Example: "Upload interrupted. Your ZIP file was corrupted. [Retry Upload] or [Contact Support]"
- Every error includes support link + expected response time
- Brand voice audit: remove jargon (no "Mission aborted"). Use "interrupted," "failed," "try again."
- Routes: `/upload` error toast, `/results/{job_id}` job failed reason
- Contact Support link: `mailto:support@snatched.app` + chat widget fallback

---

### PHASE 2: Conversion & Power Features (Weeks 4-6)
Goal: Power users get efficiency tools; Free→Pro conversion funnel activates. Keyboard adoption >30%, batch ops usage >40%, conversion 8-12%.

---

#### Phase2.1: Keyboard Shortcuts (Opt-In, Discoverable)
**Source**: B-2 | **Priority**: P1 | **Effort**: Medium

**As a** power user on my tenth job
**I want to** use keyboard shortcuts (U: upload, D: download, Ctrl+D: download all)
**So that** I complete workflows without touching mouse

**Implementation**:
- Settings > Keyboard Shortcuts: toggle [Enable Shortcuts] (off by default for new users)
- Help modal [?]: shows all shortcuts (global discovery)
- Shortcuts disabled when focus in text field (input safety)
- Keys: U (upload), D (download), Ctrl+D (download all), Ctrl+A (select all jobs), / (filter), ? (help)
- Toast hint on first Dashboard visit: "Tip: Press ? to see keyboard shortcuts"
- Show after 2nd export: `if user.exports.count >= 2: show_keyboard_toggle = true`

---

#### Phase2.2: Batch Operations (Conditional Visibility)
**Source**: B-3 | **Priority**: P1 | **Effort**: Medium

**As a** power user with 10 running jobs
**I want to** select multiple jobs and download/cancel/reprocess in bulk
**So that** I don't repeat the same action 10 times

**Implementation**:
- Dashboard: checkboxes appear when job count >= 3 (`if jobs.length >= 3: show_checkboxes = true`)
- Sticky footer: [Select All] [Clear] [Download All] [Cancel Selected] [Reprocess]
- Keyboard: Ctrl+A (all), Ctrl+D (download), Ctrl+X (cancel)
- Mobile: [Bulk Actions ▼] menu instead of checkboxes
- Storage: `selected_job_ids` in session, cleared on nav
- Route: `/dashboard`

---

#### Phase2.3: Upload Presets (Simple → System)
**Source**: B-4 | **Priority**: P1 | **Effort**: Medium

**As a** first-time uploader
**I want to** see just 2 simple toggles (Add Dates | Include Chats)
**So that** I'm not overwhelmed by options

**As a** power user on 2nd+ upload
**I want to** select pre-built presets or save custom configs
**So that** I reuse my favorite settings without re-configuring

**Implementation**:
- Route: `/upload`
- First upload: 2 toggles only: `[☑ Add dates to filenames]` `[☑ Include chat transcripts]`
- Second+ upload: Preset dropdown appears: [Standard] [Full Pipeline] [Chat-Only] + [Custom: save this config]
- Toggle state saved in `user.upload_preferences`
- Presets stored in `upload_presets` table (built-in for all; custom for Pro)
- Pro feature: Advanced presets (GPS correction, ML tagging, webhook config)

---

#### Phase2.4: Results Page Reorganization (Guided Complexity)
**Source**: B-6 (Corrections wizard) + A-1 (guided tour) | **Priority**: P1 | **Effort**: High

**As a** new user viewing results
**I want to** see what I got (Matches | Assets | Chats) + simple [Download] without 11 confusing buttons
**So that** I feel in control, not overwhelmed

**As a** power user on the same page
**I want to** access corrections, reprocessing, webhooks, filtering
**So that** I have full control in one place

**Implementation**:
- Route: `/results/{job_id}`
- Layout: Sticky header [View Results] [Download] [Corrections] [More Actions ▼]
- Tabs: Matches | Assets | Chats | Stats (collapsible)
- [Corrections] button: opens wizard (optional, hideable)
  - Wizard phases: GPS Correction → Timestamp Adjustment → Redaction → Match Re-config
  - Left sidebar: step indicators, [Next] [Back] buttons
- [More Actions ▼]: Reprocess | Export Formats | Webhooks | Tagging | Filtering
- First-time results: Guided tour overlay (dismiss [Got it] or [Skip tour])
- Tour covers: "Here's what you recovered. Click [Download] to save. [Corrections] if you need to fix GPS or timestamps."

---

#### Phase2.5: Pro Feature Gating (Gray Disable)
**Source**: C-3 | **Priority**: P1 | **Effort**: Medium

**As a** free user
**I want to** see what Pro features exist (but grayed out)
**So that** I understand what I'm missing without feeling manipulated

**As a** Pro user
**I want to** unlock these features immediately
**So that** I get value for my subscription

**Implementation**:
- Pro-locked buttons: gray background, disabled cursor
- Hover tooltip: "Available on Pro — [Upgrade]"
- Click behavior: opens upgrade modal (Stripe checkout, immediate unlock)
- When to show: immediately on buttons, but gray for free users
- When to highlight: After 1-2 exports, add contextual copy: "See what Pro unlocks" (lightbox)
- Examples: Webhooks, Custom Schemas, Advanced Presets, Batch Operations (Pro only), Friends page
- Feature flag backend: `if not user.is_pro: disable_button(feature)`

---

#### Phase2.6: Gentle Pricing Visibility
**Source**: C-1 (timing-adjusted) | **Priority**: P1 | **Effort**: Medium

**As a** first-time downloader
**I want to** feel joy about rescued memories first, *then* see pricing options
**So that** monetization doesn't interrupt my happiness

**Implementation**:
- Trigger: After `/results/{job_id}` download succeeds
- Flow: Download success toast → 2-second delay → Gentle pricing card (bottom-right, mobile: bottom modal)
- Copy: "Want more? Pro unlocks batch ops, custom schemas, and webhooks. [See Pro →]"
- Tone: helpful, not pushy ("want more?" > "your files expire")
- Frequency: show on first 3 downloads; after that, move to Settings link
- Card design: light background, small close [✕], no aggressive colors
- Link target: `/pricing` (landing page section) or upgrade modal

---

#### Phase2.7: Pro Badge in Navigation
**Source**: C-16 (progressive) | **Priority**: P1 | **Effort**: Low

**As a** returning user
**I want to** see which nav items are Pro-only (with badge)
**So that** I know what's available in my tier

**Implementation**:
- Navigation appears after 2nd export: [Friends] [Schemas] [Presets] [Webhooks]
- Each item shows [PRO] badge (small, right-aligned)
- Hover: "Available on Pro — Upgrade"
- Pro users: no badge (all items unlocked)
- Mobile [More ▼] menu: same treatment
- Routes: `/dashboard/friends`, `/dashboard/schemas`, `/upload?preset=true`, `/settings/webhooks`

---

### PHASE 3: Retention & Advanced (Weeks 7+)
Goal: Deep engagement, retention hooks, automation. 30-day retention free >60%, pro >85%.

---

#### Phase3.1: Snapchat Deadline Urgency Banner
**Source**: C-6 | **Priority**: P2 | **Effort**: Low

**As a** any user
**I want to** see a top banner with Snapchat Sept 30 deadline (empowering, not scary)
**So that** I'm motivated to export before deletion

**Implementation**:
- Route: persistent on `/dashboard`, `/results`, `/upload`
- Banner: "⏰ Snapchat deletes memories after Sept 30, 2026. Save yours now. [Learn more]"
- Tone: empowering ("save yours") not fear ("they'll delete it")
- Dismiss: [✕] button, dismissed for 7 days (cookie)
- Auto-disable: config flag, disappears after Sept 30
- Color: amber/warning (not red)

---

#### Phase3.2: Email Retention Reminders
**Source**: C-5 | **Priority**: P2 | **Effort**: Medium

**As a** user with data expiring soon
**I want to** get email reminders (7 days before, 1 day before)
**So that** I don't accidentally lose my data

**Implementation**:
- Trigger: Cron job checks `free_tier_expiry` dates
- Send: 7-day reminder + 1-day reminder (max 2 emails per user)
- Content: "Your exported memories expire in 7 days. [Download] or [Upgrade to Pro]"
- Link: direct download link (auth token) + upgrade CTA
- Frequency cap: 2/month max (no spam)
- Unsubscribe: Settings > Notifications

---

#### Phase3.3: Smart Filtering & Saved Searches
**Source**: B-15 | **Priority**: P2 | **Effort**: High

**As a** power user with 10,000 matches
**I want to** filter by confidence, strategy, date, missing data + save searches
**So that** I find specific assets without scanning everything

**Implementation**:
- Route: `/results/{job_id}` filter bar (top of Matches tab)
- Filters: confidence slider, strategy dropdown, date range, missing-data checkbox
- Save: [Save this search as...] button, store in `saved_searches` table
- List: [Saved Searches] dropdown (quick recall)
- Search API: backend SQL with WHERE clauses on indexed columns
- Mobile: collapsible filter panel

---

#### Phase3.4: Referral Program
**Source**: C-8 | **Priority**: P2 | **Effort**: Medium

**As a** user loving Snatched
**I want to** share my referral link and earn credits/upgrade months
**So that** I get value from inviting friends

**Implementation**:
- Route: `/dashboard/referrals` (appear after 1st export)
- Link: unique ref URL + copy button
- Tracking: `referrals` table, user_id + referred_user_id
- Reward: Free friend gets $10 credit; referrer gets $10 on their next bill
- Social proof: "You've referred 3 friends. They saved 500+ memories!"
- Share buttons: copy link, email, SMS

---

#### Phase3.5: Frictionless Pro Upgrade
**Source**: C-9 | **Priority**: P1 | **Effort**: Medium

**As a** free user who wants Pro
**I want to** upgrade in <60 seconds via Stripe modal
**So that** I don't abandon before completing

**Implementation**:
- Trigger: User clicks [Upgrade] or Pro-locked feature
- Modal: minimal, Stripe checkout embedded (email, card, confirm)
- Flow: Card number → Pay → Success toast → feature unlocked immediately
- Backend: webhook from Stripe updates `user.is_pro`, refreshes page
- Pricing: [Continue Free] [Upgrade to Pro: $9/month] [Contact Sales]
- Mobile: full-screen modal, simplified form

---

#### Phase3.6: Onboarding Branches (Experience Detector)
**Source**: NEW (A + B synthesis) | **Priority**: P2 | **Effort**: Medium

**As a** experienced user (migrating from v2 or Snapchat power user)
**I want to** skip the newbie tour and jump to keyboard shortcuts/presets
**So that** I don't feel patronized

**Implementation**:
- Sign-up form: "Have you used Snapchat tools before?" radio button
- NEW branch: show onboarding walkthrough + guided tour
- EXPERIENCED branch: skip walkthrough, show keyboard shortcuts toast
- Check: `user.prior_experience` flag in `user_preferences`
- Shortcut hint: "Tip: Press ? to see keyboard shortcuts"

---

## 6. CONFLICT RESOLUTIONS TABLE

| # | Conflict | Agent B | Agent C | Agent A | **FINAL DECISION** | Rationale |
|---|----------|---------|---------|---------|-------------------|-----------|
| 1 | Keyboard shortcuts | From day 1 (P0) | — | Opt-in, Phase 2 | **A: Phase 2, opt-in** | Hidden by default protects new users; discoverable via ? modal |
| 2 | Batch operations | Always visible | — | Hide until 3+ jobs | **A: Conditional** | UI clean for new users; appear when relevant, desktop/mobile diff |
| 3 | Upload presets | Day 1 (preset dropdown) | Pro-only | Phase 2 deferred | **A: Simple first (2 toggles), system later** | 90% of users need 2 options; presets unlock on 2nd export |
| 4 | Data density | 100 rows default | — | 20 rows + toggle | **A: 20 default** | Readable for new users; compact mode opt-in after 1st export |
| 5 | Pricing gate | — | Immediate (before download) | After download succeeds | **A: Post-download, gentle** | Timing = respect; user has files, then "want more?" works |
| 6 | Pro feature visuals | — | Yellow tease + badge | Gray disable | **A: Gray disable** | Honest > manipulative; gray obvious user isn't losing features |
| 7 | Tier badge placement | — | Dashboard (prominent) | Settings only | **A: Settings > Account** | No constant "free tier" reminder; quota bar on Dashboard instead |
| 8 | Pro nav features | — | All visible (C-16) | Progressive (appear after 2nd export) | **A: Progressive disclosure** | Navigation clutter prevents new user clarity; appears as capability grows |
| 9 | Onboarding | — | 4 cards (C-7) | 4 cards, skippable | **C & A: Agreed** | Mandatory first visit, [Skip] after 10 seconds; auto-skip for returns |
| 10 | Results page | Hidden in tabs | — | Wizard + tour + menu | **A: Multi-pronged** | Key actions visible [Download], advanced behind [Corrections] + [More Actions] |
| 11 | Error tone | (Implied efficient) | "Mission aborted" brand | Clear + empathetic | **A: Clear > clever** | "Upload interrupted. [Retry]" > jargon; every error has support link |
| 12 | Phase sequencing | P0 (core) | P0 (monetization) | Phased approach | **A: MVP first** | Phase 1: upload→download. Phase 2: features/monetization. Phase 3: advanced |

**Decision Rules Applied**:
1. New users win on Phase 1 UX
2. Timing > tone (same feature OK later)
3. Honesty > manipulation (gray > yellow)
4. Progressive disclosure (simple → complex as capability grows)
5. Value before ask (monetization after download)
6. Context over constant reminder (quota bar > tier label)

---

## 7. SUCCESS METRICS BY PHASE

### Phase 1 (MVP Weeks 1-3)
- **First-export completion rate**: >85% (user uploads → processes → downloads successfully)
- **Time to first download**: <15 minutes (upload + processing + download start to finish)
- **Support tickets**: <10% of users (clear onboarding reduces confusion)
- **Onboarding skip rate**: <20% (skippable but compelling)
- **Dashboard usability**: >80% users find [Upload] button on first visit

### Phase 2 (Power Features & Conversion Weeks 4-6)
- **Keyboard adoption**: >30% of power users (2+ exports) enable shortcuts
- **Batch operations usage**: >40% of power users (10+ jobs) use bulk actions
- **Free→Pro conversion rate**: 8-12% (pricing gate timing-adjusted, not aggressive)
- **Average session duration**: +25% vs Phase 1 (advanced features increase engagement)
- **Pro feature teasing effectiveness**: 15-30% CTR on [Upgrade] buttons (gray disable visible, post-1st-export)

### Phase 3 (Retention & Advanced Weeks 7+)
- **30-day retention (free tier)**: >60% (urgency banner + email reminders reduce churn)
- **30-day retention (pro tier)**: >85% (advanced features drive stickiness)
- **Referral conversion**: >5% (shared links result in new signups)
- **Keyboard penetration**: >50% of power users using shortcuts regularly
- **Saved search usage**: >20% of power users save filters for reuse

---

## 8. PAGES AFFECTED BY PHASE

### Phase 1 (Core Pages)
| Page | Route | Changes |
|------|-------|---------|
| Landing | `/` | Add onboarding modal trigger for new users |
| Onboarding | `/onboarding` | NEW: 4-card walkthrough, skippable, auto-skip mobile |
| Sign-up | `/auth/signup` | NEW: Experience detector ("Used before?" radio) |
| Dashboard | `/dashboard` | Simplified for new users (no stats badges). Empty state guidance. Sticky header with progress labels. Batch ops hidden until 3+ jobs. |
| Upload | `/upload` | Real-time validation feedback, drag-and-drop, progress bar, error recovery. First-upload preset: 2 toggles only. |
| Results | `/results/{job_id}` | Sticky header [View Results] [Download] [Corrections] [More Actions]. Guided tour overlay. Phase labels. Tabs: Matches/Assets/Chats/Stats. |
| Settings | `/settings` | New sections: Account (tier info), Notifications (email prefs), Keyboard Shortcuts toggle (hidden for new users). |

### Phase 2 (Feature Pages)
| Page | Route | Changes |
|------|-------|---------|
| Dashboard | `/dashboard` | Add [Batch Actions] sticky footer (conditional: 3+ jobs). Checkboxes appear. Stats toggle (after 2nd export). |
| Upload | `/upload` | Presets dropdown (2nd+ upload). Pro feature badges. |
| Results | `/results/{job_id}` | [Corrections] wizard visible. [More Actions] menu expanded (reprocess, webhooks, filtering). |
| Keyboard Shortcuts | `/settings/keyboard` | NEW: Toggle + full shortcut list + ? help modal. |
| Pricing | `/pricing` | NEW: Pricing page (Free/Pro/Team tiers). Landing page section or standalone. |
| Dashboard (Pro) | `/dashboard` | Pro feature pricing card (bottom-right toast after 1st download). Gentle "want more?" copy. |

### Phase 3 (Retention Pages)
| Page | Route | Changes |
|------|-------|---------|
| Dashboard | `/dashboard` | Snapchat deadline banner (persistent). Removed after Sept 30. |
| Referrals | `/dashboard/referrals` | NEW: Share link, referral stats, social proof. |
| Saved Searches | `/results/{job_id}/saved-searches` | NEW: Filter builder, save/recall interface. |
| Upgrade Flow | `/upgrade` or modal | NEW: Stripe modal, frictionless checkout. |
| Pro Dashboard | `/dashboard` (pro users) | Advanced features visible: Friends, Schemas, Webhooks (unlocked). |

---

## 9. IMPLEMENTATION SEQUENCING

### Week 1-2: Foundation
1. Onboarding walkthrough modal (Phase1.1)
2. Dashboard simplification (Phase1.2)
3. Empty state guidance (Phase1.6)
4. Settings structure (Phase1.7 + settings overhaul)

### Week 2-3: Core Workflows
5. Upload validation & feedback (Phase1.5)
6. One-click download (Phase1.3)
7. Progress labels & phase clarity (Phase1.4)
8. Error recovery templates (Phase1.7)

### Week 4: Results Page & Corrections
9. Results page reorganization (Phase2.4)
10. Corrections wizard (Phase2.4 subsection)
11. Guided tour overlay (Phase2.4 subsection)

### Week 5: Power Features
12. Keyboard shortcuts (Phase2.1)
13. Batch operations (Phase2.2)
14. Upload presets system (Phase2.3)

### Week 6: Monetization
15. Pro feature gating (Phase2.5)
16. Pricing visibility (Phase2.6)
17. Pro badge in nav (Phase2.7)

### Week 7+: Retention & Advanced
18. Snapchat deadline banner (Phase3.1)
19. Email reminders (Phase3.2)
20. Filtering & saved searches (Phase3.3)
21. Referral program (Phase3.4)

---

## 10. DEPENDENCY MAP

**Phase 1 Blockers** (must complete before launch):
- Onboarding modal (C-7)
- Dashboard simplification (B-1)
- Download button (B-5)
- Error templates (A-3)
- Database: `user_preferences` table (onboarding_seen, keyboard_enabled, stats_visibility)

**Phase 2 Blockers** (after MVP):
- Keyboard shortcuts (B-2)
- Batch operations (B-3)
- Upload presets (B-4)
- Results page refactor (B-6 + A-1)
- Stripe integration (C-1, C-9)
- Database: `upload_presets` table, `saved_searches` table, `referrals` table

**Phase 3 Blockers** (after Phase 2):
- Email service + cron (C-5)
- Filtering API (B-15)
- Referral tracking (C-8)

---

## 11. DECISION FRAMEWORK FOR CONFLICTS

Use this framework if new conflicts arise during implementation:

1. **Does this feature confuse new users in Phase 1?** → Defer to Phase 2
2. **Is timing more important than tone?** → Choose better timing
3. **Does this feel manipulative?** → Use honest visual treatment (gray > yellow)
4. **Is this visible when user capability doesn't justify it?** → Use progressive disclosure
5. **Does monetization come before user value?** → Reorder (value first)
6. **Is this a constant nag or contextual?** → Make contextual

---

## Document Metadata

- **Owner**: Product Team (Agent A, B, C consensus)
- **Last Updated**: 2026-02-24
- **Status**: Ready for Implementation
- **Implementation Start**: 2026-03-01 (estimated)
- **Approval**: All three agents approve consensus approach
- **Design Docs Needed**: UI mockups for Phase1.2 (Dashboard), Phase2.4 (Results), Phase2.5 (Pro gates)
- **Engineering Docs Needed**: Routes/endpoints, database schema updates, Stripe integration spec
