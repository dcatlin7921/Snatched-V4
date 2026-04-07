# Snatched v3 UX Debate — Consensus Matrix

**Purpose**: Quick-reference table showing proposed resolutions for each conflict
**Format**: Each row = one conflict; shows Agent positions + proposed compromise
**Date**: 2026-02-24

---

## Feature Visibility Conflicts

### Conflict 1: When to Show Keyboard Shortcuts
| Aspect | Agent B Position | Agent C Position | Agent A Position | PROPOSED RESOLUTION |
|--------|------------------|------------------|------------------|-------------------|
| **When visible** | From signup (day 1) | N/A | Hidden until 2nd export | **Hidden by default; opt-in via Settings** |
| **Discovery** | Tooltip on hover | N/A | Help modal (?) | **Help modal is primary; toast hints on first action** |
| **Safety** | No protection | N/A | Must not fire in text inputs | **Keyboard shortcuts disabled when focus in input field** |
| **Decision** | ✗ B's approach hurts new users | — | ✅ **A's conditional approach wins** | |
| **Implementation** | — | — | — | **Settings > Keyboard Shortcuts toggle (off by default for new users)** |

**Rationale**: Keyboard shortcuts are powerful for power users but accidentally triggered shortcuts confuse new users. Hiding by default with easy discovery (? modal) protects new users while letting power users self-select.

---

### Conflict 2: When to Show Batch Operations
| Aspect | Agent B Position | Agent C Position | Agent A Position | PROPOSED RESOLUTION |
|--------|------------------|------------------|------------------|-------------------|
| **Default visibility** | Always show checkboxes | N/A | Hide until 3+ jobs | **Hide until 3+ jobs visible** |
| **UI presence** | Checkboxes on every card | N/A | Appear only when relevant | **Checkboxes hidden; appear when Dashboard shows 3+ jobs** |
| **Sticky footer** | Always ready | N/A | Only after selection | **Footer hidden until user selects 1+ jobs** |
| **Mobile UX** | Not specified | N/A | Nested in menu | **Mobile: [Bulk Actions ▼] menu; Desktop: checkboxes** |
| **Decision** | ✗ B's always-on clutter | — | ✅ **A's conditional approach wins** | |
| **Implementation** | — | — | — | **JavaScript: Show checkboxes when job count >= 3** |

**Rationale**: New user with 1 job sees no checkboxes (clean UI). Power user with 10 jobs sees checkboxes (relevant feature). Reduces cognitive load on new users; enables efficiency for power users.

---

### Conflict 3: Upload Presets — First Upload vs. Later
| Aspect | Agent B Position | Agent C Position | Agent A Position | PROPOSED RESOLUTION |
|--------|------------------|------------------|------------------|-------------------|
| **First upload UX** | Preset dropdown | C-19: Pro feature | Simple toggles only | **2 toggles: [☑ Add dates] [☑ Include chats]** |
| **Second+ uploads** | Preset dropdown | C-19: Save configs | Preset system unlocked | **Preset dropdown appears; saved configs available** |
| **Cognitive load** | Assumes power user | Assumes Pro user | Protects new user | **New users see simple; repeat users see efficiency** |
| **Presets available when?** | From day 1 | Pro only | After 2nd export | **After 2nd export; built-in presets for all, custom for Pro** |
| **Decision** | ✗ B's preset paralysis | ✗ C's tier lock | ✅ **A's deferred approach wins** | |
| **Implementation** | — | — | — | **First upload: 2 toggles. Second upload+: Dropdown to [Standard] [Full Pipeline] [Chat-Only] + custom.** |

**Rationale**: New users uploading for the first time don't know what "preset" means. Showing two simple options (dates + chats) is 90% of what users need. Power users on second export get full system. Tier gating can still apply to advanced presets (Pro-only).

---

### Conflict 4: Data Density (Compact Mode)
| Aspect | Agent B Position | Agent C Position | Agent A Position | PROPOSED RESOLUTION |
|--------|------------------|------------------|------------------|-------------------|
| **Default rows/page** | 100 rows | N/A | 20 rows | **20 rows default** |
| **Font size** | 0.875rem (small) | N/A | 1rem (readable) | **1rem default; 0.875rem in compact mode** |
| **Column customization** | Always visible | N/A | Hidden toggle | **Toggle: "Customize columns" (reveals after first export)** |
| **Compact mode toggle** | Not mentioned | N/A | Hidden until 2nd export | **[Compact View] toggle appears after first export** |
| **Decision** | ✗ B's density confuses new users | — | ✅ **A's progressive approach wins** | |
| **Implementation** | — | — | — | **Default: 20 rows, 1rem, key columns. Toggle [Compact] to 100 rows, 0.875rem, all columns.** |

**Rationale**: New user with 347 matches needs readability, not density. Compact mode is opt-in for power users who know what they're looking for. After user completes first export, they can toggle to compact if desired.

---

## Monetization & Conversion Conflicts

### Conflict 5: Pricing Gate — When & How
| Aspect | Agent B Position | Agent C Position | Agent A Position | PROPOSED RESOLUTION |
|--------|------------------|------------------|------------------|-------------------|
| **When shown** | N/A | On download page (immediate) | After download succeeds | **Show after download completes, not before** |
| **Timing in flow** | N/A | "Sticky card in bottom-right" | "User is in happy moment" | **After file is in user's hands, not mid-action** |
| **Tone** | N/A | Urgent ("memories expire") | Helpful ("want more?") | **Gentle: "Want more? Pro unlocks..."; not "your files expire"** |
| **Frequency** | N/A | Every download | Only first 2-3 | **Show on first 3 downloads; then move to Settings** |
| **Decision** | — | ✗ C's timing too aggressive | ✅ **A's timing + tone compromise** | |
| **Implementation** | — | — | — | **After download success: Toast celebration → 2-second delay → Gentle pricing card (bottom-right, mobile: modal)** |

**Rationale**: User who just rescued memories is in an emotional high. Showing monetization *during* that moment interrupts the joy. *After* the download is safe in their hands, a gentle "want more?" is well-timed and respectful. Conversions still happen (C's goal achieved) without manipulating users (A's concern addressed).

---

### Conflict 6: Pro Feature Visibility — Tease vs. Hide
| Aspect | Agent B Position | Agent C Position | Agent A Position | PROPOSED RESOLUTION |
|--------|------------------|------------------|------------------|-------------------|
| **Visual treatment** | N/A | Yellow outline + Pro badge | Gray disable | **Gray disable (more honest)** |
| **Hover behavior** | N/A | "Available on Pro" tooltip | No teasing | **Hover shows: "Available on Pro — Upgrade"** |
| **When visible** | N/A | Immediately (all users) | After 1-2 exports | **Show immediately on buttons, but gray for free users** |
| **Click behavior** | N/A | Opens upgrade modal | Opens upgrade modal | **Upgrade modal (agreed)** |
| **Conversion lift** | N/A | 15-30% (C cites) | Lower (user not ready) | **Agreed: 15-30% is real, but defer to post-1st-export to avoid suspicion** |
| **Decision** | — | ✗ C's yellow tease feels manipulative | ✅ **A's gray + timing is transparent** | |
| **Implementation** | — | — | — | **Pro buttons gray by default. After user completes 1 export: button stays gray but copy adds urgency ("See what Pro unlocks")** |

**Rationale**: "Yellow tease" implies manipulation ("you're missing out!"). Gray disable is honest ("this isn't available to you"). After user has felt value once, they're more receptive to feature upgrades. Conversion rate still hits 15%+ because timing is right.

---

### Conflict 7: Tier Badge & Quota Display
| Aspect | Agent B Position | Agent C Position | Agent A Position | PROPOSED RESOLUTION |
|--------|------------------|------------------|------------------|-------------------|
| **Where shown** | N/A | Dashboard (prominent card) | Settings > Account only | **Settings > Account; quota bar on Dashboard** |
| **Frequency** | N/A | Always visible | Contextual only | **Dashboard shows storage meter (not tier label); full tier info in Settings** |
| **Urgency trigger** | N/A | 80%+ quota = warning badge | Never proactive | **Show storage bar; at 80% add: "Running out? Upgrade"** |
| **New user view** | N/A | "Your Plan: Free" + upgrade button | No tier pressure | **No tier label on Dashboard for new users** |
| **Decision** | — | ✗ C's constant reminder feels nagging | ✅ **A's contextual approach** | |
| **Implementation** | — | — | — | **Dashboard: Storage meter (6.8 GB / 10 GB). Tap to go to Settings > Quota. Settings shows "Your Plan: Free" + upgrade CTA.** |

**Rationale**: Seeing "Free Tier" on every Dashboard visit is a constant reminder that you're on free tier. It's demotivating. Showing a storage meter (visual, not text) is informative without guilt. At 80%, context makes upgrade feel necessary, not nagging.

---

### Conflict 8: Pro Features in Navigation
| Aspect | Agent B Position | Agent C Position | Agent A Position | PROPOSED RESOLUTION |
|--------|------------------|------------------|------------------|-------------------|
| **Navigation visibility** | N/A | All features visible (Friends, Schemas, Presets) | Hide from new users | **Progressive: New users see Upload | Dashboard | Settings. Features appear after 2nd export or upgrade.** |
| **Pro badge on nav** | N/A | Yes, small badge | No badge (hidden) | **Badge shown when feature becomes visible** |
| **Hover tooltip** | N/A | "Available on Pro — [Upgrade]" | None | **Tooltip on Pro-badged nav items** |
| **Mobile UX** | N/A | Not specified | Not specified | **Mobile: Friends/Schemas/Presets in [More ▼] menu** |
| **Decision** | — | ✗ C's always-visible nav overwhelms new users | ✅ **A's progressive approach** | |
| **Implementation** | — | — | — | **New users (first 30 days): Nav = Upload | Dashboard | Settings. After 2nd export: Add [Friends] [Schemas] [Presets] (Pro badge on each).** |

**Rationale**: New user sees navigation with 6 items (Friends, Schemas, Presets, API Keys, etc.). Questions: "What's a schema?" "Do I need friends?" → confusion. Navigation clutter. Show features progressively as user capability increases.

---

## New User Experience Conflicts

### Conflict 9: Onboarding — Mandatory or Optional
| Aspect | Agent B Position | Agent C Position | Agent A Position | PROPOSED RESOLUTION |
|--------|------------------|------------------|------------------|-------------------|
| **Mandatory?** | N/A | Yes, 4-card walkthrough | Mandatory, but skippable | **Mandatory first visit; skippable after 10 seconds** |
| **Content** | N/A | What | Safety | Tiers | Ready | Simplified: What + Why Safe + Get Started | **4 cards (C's scope); first card auto-skips after 10s for mobile** |
| **Repeat users** | N/A | Auto-skip | Auto-skip | **Auto-skip for returning users (check user created_at)** |
| **Mobile UX** | N/A | Full width modal | Full width, swipe-able | **Full width, single-column, thumb-friendly buttons** |
| **Decision** | — | ✅ C & A agree on core approach | ✅ **A & C aligned** | |
| **Implementation** | — | — | — | **Jinja2 conditional: If user.jobs.count == 0, show onboarding modal. [Skip] button always visible. Auto-skip after 10 seconds.** |

**Rationale**: New users *need* onboarding (prevents confusion). But they also need escape routes (if they're experienced or impatient). 10-second auto-skip respects both needs. Returning users don't see it again (checked via user metadata).

---

### Conflict 10: Results Page Intimidation
| Aspect | Agent B Position | Agent C Position | Agent A Position | PROPOSED RESOLUTION |
|--------|------------------|------------------|------------------|-------------------|
| **Current problem** | "11 action buttons" | (Implicit: confusing for new users) | Overwhelming for first-timers | **Agreed: Current Results page is cluttered** |
| **B's solution** | B-6 (Correction wizard) | N/A | Make wizard optional | **Wizard exists but hidden behind [Corrections] button** |
| **A's solutions** | — | — | A1 (guided tour) + A2 (empty state) | **Add guided tour overlay + simple empty state messaging** |
| **Consolidation** | N/A | N/A | Hide advanced actions behind menu | **Results: Key sections (Matches | Assets | Chats) + [More Actions ▼] menu** |
| **Decision** | — | — | ✅ **A's multi-pronged approach** | |
| **Implementation** | — | — | — | **Results sticky header: [View Results] [Download] [Corrections] [More Actions ▼]. First visit: Guided tour overlay. First export: Celebratory context.** |

**Rationale**: Results page needs triage. New users need: "Here's what you got, here's how to download." Advanced users need: Corrections, reprocessing, webhooks. Solution: Keep key actions visible, hide advanced stuff in [More Actions] menu + optional Corrections wizard.

---

## Copy & Tone Conflicts

### Conflict 11: Error Message Tone
| Aspect | Agent B Position | Agent C Position | Agent A Position | PROPOSED RESOLUTION |
|--------|------------------|------------------|------------------|-------------------|
| **Tone** | (Implied: efficient) | "Rebellion brand voice" | Empathy + clarity | **Warm, clear, active voice** |
| **Example (C's)** | — | "Mission aborted" | "Upload interrupted" | **"Upload interrupted" (clearer for new users)** |
| **Formula** | — | Brand voice consistency | "What | Why | What Now" | **All errors follow: Problem + Reason + Next Action** |
| **Support link** | — | (Not mentioned) | In every error | **Every error: "Contact support [link]" with response time** |
| **Decision** | — | ✗ C's "mission aborted" is jargon | ✅ **A's clear + empathetic** | |
| **Implementation** | — | — | — | **Error template: [⚠️ icon] What happened (plain English). Why. [Next Action Button] or [Contact Support].** |

**Rationale**: New users see error messages and feel lost. "Mission aborted" is confusing (what mission?). "Upload interrupted. [Retry] or [Contact Support]" is clear. C's brand voice is great *where it fits*, but error messages need clarity over cleverness.

---

## Implementation Sequencing Conflicts

### Conflict 12: Phase 1 vs. Phase 2 Features
| Feature | Agent B Timing | Agent C Timing | Agent A Timing | PROPOSED RESOLUTION |
|---------|---|---|---|---|
| **Keyboard shortcuts** | P0/P1 (critical) | N/A | Phase 2 (after 2 exports) | **Phase 2: Launch with foundation, add after MVP** |
| **Batch operations** | P0/P1 (critical) | N/A | Phase 2 (when 3+ jobs exist) | **Phase 2: Same reasoning** |
| **Pricing messaging** | N/A | P0 (critical) | Phase 1 (after success) | **Phase 1: After download, gentle. Phase 2: Upgrade modal.** |
| **Pro feature teasing** | N/A | P0 (critical) | Phase 2 (after 1st export) | **Phase 2: Gray disable visible, teasing copy added post-1st-export** |
| **Decision** | ✗ B's P0 adds MVP complexity | ✗ C's P0 adds monetization burden | ✅ **A's phased approach** | |
| **Rationale** | — | — | MVP = new user flow (upload → process → download). Features/monetization come after user feels value. | |

**Consequence**:
- **Phase 1 (MVP, Weeks 1-3)**: Onboarding, Dashboard, Download, Corrections wizard (optional), Brand voice, Settings safety, Guided tour, Empty states, Error recovery
- **Phase 2 (Weeks 4-6)**: Keyboard shortcuts, Batch operations, Presets, Pro feature teasing (gray), Pricing page, Frictionless upgrade
- **Phase 3+ (Weeks 7+)**: Advanced features (filtering, webhooks, tagging, comparison, schemas, friends)

---

## Summary Table: All Conflicts & Resolutions

| # | Conflict | Agent B | Agent C | Agent A | DECISION | Rationale |
|---|----------|---------|---------|---------|----------|-----------|
| 1 | Keyboard shortcuts | From day 1 | N/A | Opt-in, Phase 2 | **A wins** | Hidden by default protects new users |
| 2 | Batch operations | Always show | N/A | Conditional (3+ jobs) | **A wins** | UI clean for new users; available when needed |
| 3 | Upload presets | Day 1 | C-19 Pro | Phase 2 deferred | **A wins** | Simple first (2 toggles), system later |
| 4 | Data density | 100 rows | N/A | 20 rows + toggle | **A wins** | Readable default, power users self-select |
| 5 | Pricing gate | N/A | Immediate | After success | **A wins** | Timing = respect for user's moment |
| 6 | Pro teasing | N/A | Yellow outline | Gray disable + timing | **A wins** | Honest visual, better timing |
| 7 | Tier badge | N/A | Dashboard | Settings only | **A wins** | No constant reminder; contextual helps |
| 8 | Pro nav features | N/A | All visible | Progressive | **A wins** | Navigation clutter prevents new user clarity |
| 9 | Onboarding | N/A | 4 cards | 4 cards, skippable | **C & A** | Agreed approach |
| 10 | Results intimidation | Wizard (opt) | N/A | Wizard + tour + menu | **A wins** | Multi-pronged approach: hide, guide, explain |
| 11 | Error tone | (Implied) | "Mission aborted" | Clear + empathetic | **A wins** | Jargon-free > clever copy |
| 12 | Phase sequencing | Phase 0 | Phase 0 | Phased approach | **A wins** | MVP first, features/monetization after value |

---

## Decision Rules Applied

1. **New users always win on Phase 1 UX** — If a feature confuses new users, defer it to Phase 2.
2. **Timing beats tone** — The *same feature* (pricing gate, Pro tease) is OK later but problematic earlier.
3. **Honesty beats manipulation** — Gray disable > yellow tease; plain English > brand jargon in errors.
4. **Progressive disclosure** — Show features as user capability increases, not all at once.
5. **Value before ask** — User must feel value (rescued memories) before monetization messaging.
6. **Context over constant reminder** — Storage meter contextually useful; "free tier" label constantly nagging.

---

## Approval Status

| Agent | Consensus Agreement | Notes |
|-------|-------------------|-------|
| **Agent A** | ✅ Proposed this consensus | Author of compromise framework |
| **Agent B** | ⏳ Pending | Some deferral of P0→P2 may be negotiable; keyboard shortcuts deferral especially |
| **Agent C** | ⏳ Pending | Pro feature visibility (gray vs. hidden) & timing (phase 2 vs. phase 1) needs discussion |

**Next Step**: Agents B & C review this matrix, flag objections, negotiate remaining points.

---

**Document Owner**: Agent A
**Status**: Draft consensus for approval
**Target Approval Date**: 2026-02-26
**Implementation Start**: 2026-03-01
