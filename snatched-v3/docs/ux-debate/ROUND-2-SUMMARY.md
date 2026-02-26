# Snatched v3 UX Debate — Round 2 Summary

**Status**: All three agents have submitted perspectives
**Date**: 2026-02-24
**Next Step**: Consensus negotiation

---

## Round 2 Submissions

| Agent | File | Focus | Stories |
|-------|------|-------|---------|
| **Agent A** (New User Advocate) | `AGENT-A-ROUND-2-RESPONSE.md` | Simplicity, confidence, zero-friction onboarding | 20 baseline + 3 new |
| **Agent B** (Power User Champion) | `AGENT-B-POWER-USER-STORIES.md` | Efficiency, keyboards, batch ops, automation | 20 stories |
| **Agent C** (Product Strategist) | `ux-stories-product-strategist.md` | Conversion, retention, monetization, brand voice | 20 stories |

---

## Key Conflicts Identified

### 1. When to Show Features (Visibility Timing)
| Feature | Agent B | Agent C | Agent A | Consensus? |
|---------|---------|---------|---------|-----------|
| Keyboard shortcuts | From day 1 | N/A | Opt-in, hidden for first 2 jobs | **A3 strategy: progressive disclosure** |
| Batch operations | Always visible | N/A | Show when 3+ jobs exist | **A3 strategy: conditional visibility** |
| Upload presets | First upload | N/A | Second upload+ | **A3 strategy: deferred** |
| Pro features in nav | N/A | All features, Pro badges | Simple nav for new users, advanced later | **A3 strategy: progressive disclosure** |
| Pricing messaging | N/A | Immediate (download page) | After first download succeeds | **A3 timing compromise** |

### 2. Data Density (UX vs. Power)
| Aspect | Agent B | Agent C | Agent A | Consensus? |
|--------|---------|---------|---------|-----------|
| Default rows/page | 100 compact | N/A | 20 readable | **Default 20, opt-in to 100** |
| Column customization | Yes | N/A | Hidden toggle | **Toggle after first export** |
| Font size | 0.875rem | N/A | 1rem (readable) | **Default 1rem, compact at 0.875rem** |

### 3. Monetization Tone (Conversion vs. Trust)
| Tactic | Agent B | Agent C | Agent A | Consensus? |
|--------|---------|---------|---------|-----------|
| Feature teasing | N/A | Yellow outline on locks | Gray disable, show after 1-2 exports | **Gray disable + timing** |
| Pricing urgency | N/A | High (sticky card, banner) | Gentle (after success, not before) | **Both: gentle first, urgent later** |
| Tier badge placement | N/A | Dashboard card | Settings only | **Settings > Account** |
| Upgrade modal | N/A | Overlay, <60s flow | Contextual (triggered by feature lock) | **Both: modal overlay, triggered by interest** |

### 4. Corrections Workflow (Mandatory vs. Optional)
| Aspect | Agent B | Agent A | Consensus? |
|--------|---------|---------|-----------|
| Seamless pipeline | Wizard with steps (GPS → TS → Redact → Config) | Optional [Corrections] button | **Make wizard optional, hide behind button** |
| New user exposure | Always visible | Hidden until user needs corrections | **Hidden by default** |

### 5. Onboarding & Education
| Aspect | Agent A | Agent C | Consensus? |
|--------|---------|---------|-----------|
| Pre-upload walkthrough | ✅ Mandatory (4 cards) | ✅ Proposed (C-7) | **Agreed: 4-card onboarding** |
| Skippable? | After 10 seconds | Doesn't specify | **Skippable after 10 seconds** |
| Results page tour | ✅ New Story A1 (guided) | N/A | **New story: guided Results tour** |
| Empty state guidance | ✅ New Story A2 | N/A | **New story: empty state education** |

---

## Stories Agreed Upon (No Conflict)

### Universally Supported
1. **C-7: Onboarding Flow Before Upload** — All agents agree this is critical
2. **B-5: One-Click Download from Dashboard** — All agents support; reduces friction
3. **B-6: Correction Workflow as Pipeline** — B wants it; A makes it optional; C indifferent; net: **approved**
4. **C-12: Settings Separation (Account vs. Danger)** — All agents support safety
5. **C-14: Brand Voice Consistency** — All agents support quality
6. **B-1: Dashboard as Command Center** — All agents support; A adds "simplified" caveat

### Agent B Stories with A Guardrails
- **B-2: Keyboard Shortcuts** → Opt-in, hidden for new users, discoverable via `?`
- **B-3: Batch Operations** → Show only when 3+ jobs on Dashboard
- **B-4: Upload Presets** → Simple toggles (first upload), presets (second upload+)
- **B-10: Compact Data Density** → Opt-in toggle after first export

### Agent C Stories with Timing Adjustment
- **C-1: Pricing Gate** → Show after first *download completes*, not before
- **C-3: Pro Feature Teasing** → Use gray disable instead of yellow tease; show after 1-2 exports
- **C-4: Tier Badge** → Move from Dashboard to Settings > Account
- **C-6: Urgency Messaging** → Gentle tone ("help"), not fear ("delete")

### New Stories (Agent A)
- **A1: Guided Results Page Tour** — Help new users understand match data
- **A2: Empty States & Progressive Education** — Clear CTA on empty Dashboard
- **A3: Error Recovery & Empathy** — Plain English errors + next steps

---

## Proposed Implementation Roadmap

### Phase 1: MVP New User Path (Weeks 1-3)
**Goal**: Ship a product where a *new user* can upload, process, and download **without confusion**.

**Stories to implement**:
1. C-7 (Onboarding)
2. B-1 (Dashboard, simplified)
3. B-5 (One-click download)
4. C-1 (Pricing gate, after success)
5. B-6 (Corrections wizard, optional)
6. C-14 (Brand voice audit)
7. C-12 (Settings separation)
8. A1 (Guided Results tour)
9. A2 (Empty state guidance)
10. A3 (Error recovery)

**Effort**: ~4-5 weeks (front-end + copy)
**Outcome**: New users feel confident; support tickets drop; first-export completion rate increases

### Phase 2: Power User Unlock (Weeks 4-6)
**Goal**: Once users trust the product, unlock advanced features.

**Stories to implement**:
1. B-2 (Keyboard shortcuts, opt-in)
2. B-3 (Batch operations, conditional)
3. B-4 (Upload presets, deferred)
4. C-3 (Pro feature teasing, gray disable)
5. C-2 (Landing page pricing section)

**Effort**: ~2-3 weeks
**Outcome**: Power users get efficiency; returning users discover advanced features naturally

### Phase 3: Advanced & Monetization (Weeks 7-10)
**Goal**: Serve power users and optimize retention/conversion.

**Stories to implement**:
1. C-9 (Frictionless upgrade flow)
2. B-15 (Filtering & saved searches)
3. C-5 (Email retention reminders)
4. B-7 (Job groups)
5. B-8 (Advanced match config)
6. B-12 (Selective reprocessing)
7. B-17 (Webhooks & automation)

**Effort**: ~3-4 weeks
**Outcome**: Monetization loop closed; power users have tools; retention increases

---

## Top 15 Stories (Unified Priority, Agent A Recommendation)

| Rank | Story | Agent | Phase | Why |
|------|-------|-------|-------|-----|
| 1 | C-7: Onboarding | C | 1 | Critical path; reduces confusion |
| 2 | B-1: Dashboard (simplified) | B | 1 | Clean home; new users need calm entry |
| 3 | B-5: One-click download | B | 1 | Easiest path to files after success |
| 4 | C-1: Pricing after success | C | 1 | Monetization, good timing |
| 5 | B-6: Corrections wizard | B | 1 | Reduces intimidating 11-button Results page |
| 6 | C-14: Brand voice | C | 1 | Consistency = trust (new users notice) |
| 7 | C-12: Settings separation | C | 1 | Safety; prevents accidental deletion |
| 8 | B-2: Keyboard shortcuts (opt-in) | B | 2 | Power user efficiency, safe for new users |
| 9 | B-3: Batch operations (conditional) | B | 2 | Scale support, hidden until relevant |
| 10 | B-4: Upload presets (deferred) | B | 2 | Repeat user convenience, simple first |
| 11 | C-3: Pro feature teasing (refined) | C | 2 | Conversion, gentle timing |
| 12 | C-2: Landing page pricing | C | 2 | Pre-commit transparency |
| 13 | C-9: Frictionless upgrade | C | 3 | Conversion flow <60 seconds |
| 14 | B-15: Filtering & saved searches | B | 3 | Power user feature discovery |
| 15 | C-5: Email retention reminders | C | 3 | Churn reduction via lifecycle email |

**New Stories (A1, A2, A3)** are folded into Phase 1, as detailed above.

---

## Open Questions for Final Consensus

1. **Onboarding: Mandatory or Skippable?**
   - A proposes: Skippable after 10 seconds (avoid friction for experienced users)
   - C proposed: 4-card walkthrough (for new users only)
   - **Recommend**: Skippable after 10 seconds, repeatable via ? help modal

2. **Error Tone: Empathy or Efficiency?**
   - A emphasizes: Plain English + next steps + support link
   - B emphasizes: Quick recovery (implied)
   - C emphasizes: Brand voice consistency
   - **Recommend**: Error messages follow A3 formula (What | Why | What Now)

3. **Feature Disclosure: Gray Disable or Hide?**
   - A proposes: Gray disable for Pro features (discoverable)
   - C proposes: Yellow tease with hover tooltip
   - **Recommend**: Gray disable (less manipulative, still discoverable)

4. **Pricing Timing: First Download or Second Export?**
   - A proposes: After first download (user is happy)
   - C proposes: On download page (highest-intent moment)
   - **Recommend**: After first download completes (timing compromise)

5. **Data Density Default: 20 or 100 rows?**
   - B proposes: 100 rows default (power users)
   - A proposes: 20 rows default (new users)
   - **Recommend**: 20 default, toggle to compact (100 rows) after first export

---

## Metrics for Success (Post-Launch)

### New User Metrics
- First-export completion rate (target: 85%+ of signups → successful download)
- Time to first download (target: <15 minutes from upload)
- Support ticket rate (target: <10% of users)
- Confusion about features (measured via feedback form, target: <5%)

### Power User Metrics
- Keyboard shortcut adoption (target: 40%+ of returning users)
- Batch operation usage (target: 30%+ of power users with 3+ jobs)
- Preset save rate (target: 50%+ of second+ uploads)

### Monetization Metrics
- Free→Pro conversion rate (target: 8-12% after first export)
- Churn rate (30-day retention, target: 60%+ for free, 85%+ for Pro)
- Email re-engagement effectiveness (target: 5-10% of churned users reactivated)

---

## Next Steps

1. **Consensus Meeting**: All three agents discuss conflicts and agree on final approach
2. **Design Kick-off**: Wireframe Phase 1 (onboarding, dashboard, download)
3. **Copy Audit**: Brand voice consistency pass on all modals and toasts
4. **Implementation Sprint**: Phase 1 (4-5 weeks)
5. **Launch & Measure**: Track metrics listed above
6. **Iterate**: Phase 2 features based on Phase 1 user behavior

---

**Document Owner**: Agent A (New User Advocate)
**Consensus Required By**: 2026-02-26 (48 hours)
**Implementation Start**: 2026-03-01

---
