# Snatched v3 UX Debate — Round 2 Executive Summary

**Participants**: Agent A (Casual User), Agent B (Power User), Agent C (Accessibility)
**Date**: 2026-02-24
**Total Stories Across All Agents**: 60 (20 per agent)
**Status**: Ready for Consensus Phase

---

## THE BIG PICTURE

Three personas, three priorities:

| Agent | Persona | Focus | Key Stories |
|-------|---------|-------|------------|
| **A** | Casual/Beginner | Onboarding, clarity, hand-holding | Landing page, auth, drag-and-drop, phase labels, empty states, help |
| **B** | Power User | Efficiency, control, automation | Dashboard as command center, keyboard shortcuts, batch ops, webhooks, presets |
| **C** | Accessibility/Retention | Inclusive design, engagement, deadline urgency | WCAG compliance, clear voice, retention emails, upgrade transparency, deadline banner |

---

## AGENT B'S CONSENSUS POSITION

### What I Enthusiastically Support from A & C

**From Agent A** (7 stories):
- A-2: Sign-up happy path (onboarding matters)
- A-4: Drag-and-drop feedback (power users upload large ZIPs)
- A-7: Phase labels (clarity helps debugging)
- A-12: Empty state guidance (prevents churn)
- A-14: Error recovery (friendly messages save debugging)
- A-19: Post-download guides (Immich integration matters)
- A-20: Tooltips & help (discoverability)

**From Agent C** (7 stories):
- C-3: Pro feature badges (transparency)
- C-6: Snapchat deadline banner (urgency → engagement)
- C-10: Social proof (community validation)
- C-11: Feedback/ratings (product improvement)
- C-15: Re-engagement emails (retention)

**Bottom line**: These 14 stories don't slow power users down. They're *enablers*. Casual users land safely, power users stay engaged, everyone understands what's free vs. Pro.

### What I Have Concerns About (with Compromises)

**From Agent A**:
- **A-16 (Tour)**: ⚠️ Make it dismissible and opt-in. Show only on first visit. Branch to skip if user has v2 experience.
- **A-3 (Upload guide)**: ⚠️ Collapse by default for returning users. Expand for true first-timers.
- **A-8 (Results tabs)**: ⚠️ Compromise: Expert mode toggle. Power users can see all buttons at once.
- **A-13 (Quota limits)**: ⚠️ Show before submit, not mid-operation.
- **A-15 (Mobile)**: ⚠️ OK for mobile, don't let it compromise desktop nav (desktop nav stays visible).

**From Agent C**:
- **C-2 (OIDC)**: ⚠️ Use long token TTL (8-12h), silent refresh. Don't force re-auth mid-session.
- **C-13 (Settings tabs)**: ⚠️ Dashboard quick-access card solves this. Users shouldn't have to navigate tabs.
- **C-12 (Brand voice)**: ⚠️ Professional + friendly. Avoid patronizing tone.
- **C-5 (Upgrade modal)**: ⚠️ Click to upgrade (not hover). Keep modal small and fast.
- **C-7 (Emails)**: ⚠️ Cap at 2/month max.
- **C-16 (Pro badges)**: ⚠️ Only badge fully-locked features, not "higher tier limits."

**Bottom line**: All concerns are *solvable with good design*. None require sacrificing power user experience.

---

## TOP 15 UNIFIED ROADMAP

**Tier 1: Critical Foundation (Weeks 1-3)**
1. **A-1**: First-Time Hero Visual (landing page — everyone needs this)
2. **B-1**: Dashboard as Command Center (core power user experience)
3. **A-2**: Sign-Up/Login Happy Path (auth flow)
4. **A-3**: Upload Drag-and-Drop (validation + feedback)
5. **B-2**: Keyboard-First Navigation (power user efficiency)
6. **B-5**: One-Click Download (eliminates Results page clicks)
7. **A-7**: Progress Phase Labels (clarity)

**Tier 2: Power User Consolidation (Weeks 4-6)**
8. **B-3**: Batch Operations (multi-select, bulk actions)
9. **B-6**: Correction Workflow Pipeline (GPS → Timestamps → Redact → Match Config as one wizard)
10. **C-3**: Locked Features + Upgrade Modal (transparent monetization)
11. **A-12**: Empty State Guidance (prevents churn)
12. **B-4**: Upload Presets (config reuse)
13. **A-19**: Post-Download Celebration (Immich guides)
14. **A-20**: Contextual Help & Tooltips (discoverability)
15. **C-6**: Urgency Banner (Snapchat deadline)

---

## THREE EMERGING STORIES (NEW)

Developed from cross-agent synthesis:

### NEW 1: Lazy-Load Heavy Tables with Progressive Disclosure
- **Why**: B needs 5,000 rows without cognitive overload. A needs gradual disclosure. Solution: Load first 20, then stream. [Show All] button for power users.
- **Priority**: P1
- **Effort**: MEDIUM

### NEW 2: Guided Power User Onboarding (Branching Path)
- **Why**: A wants tour (onboarding). B wants to skip. Solution: Sign-up asks "New or experienced?" and branches. NEW users → A-16 tour. EXPERIENCED → B-2 shortcuts hint.
- **Priority**: P1
- **Effort**: MEDIUM

### NEW 3: Smart Notifications (Summary vs. Real-Time)
- **Why**: B wants instant desktop notifications for job completion. C wants email retention reminders. Solution: User preference. Desktop users get push. Mobile users get daily digest email.
- **Priority**: P2
- **Effort**: MEDIUM

---

## DESIGN PRINCIPLES FOR UNIFIED EXPERIENCE

1. **Bifurcated Complexity**: Casual and power users coexist. Casual users see simplified Dashboard. Power users toggle "Expert Mode" for all options. Both available simultaneously.

2. **Progressive Onboarding**: First-time users get guided experience. Returning users skip. Branching based on experience level (NEW 2).

3. **Transparent Tiers**: Pro features clearly marked. Upgrade is frictionless when user decides they need it.

4. **Keyboard + Mouse Parity**: Both input methods are first-class. Shortcuts are discoverable via ? modal.

5. **Retention via Urgency + Value**: Sept deadline is real. In-app banner + capped email reminders keep users engaged. Real value (batch ops, webhooks) keeps them coming back.

6. **Context-Aware Complexity**: Results page buttons visible (not hidden in tabs) or togglable via expert mode. Matches table lazy-loads first 20, then streams. Keyboard shortcuts only active when not typing in text fields.

---

## OUTSTANDING QUESTIONS FOR FINAL CONSENSUS

1. **Results Page Layout**: All buttons visible + icon-only design, or grouped tabs + expert toggle?
2. **Tour Frequency**: Only on first login, or every new sign-up?
3. **Keyboard Shortcut Conflicts**: Context-aware (only active when not in text field)?
4. **Mobile vs. Desktop**: Two distinct experiences, or single responsive design?
5. **Notification Frequency**: Real-time desktop + daily digest email? Weekly summary?

---

## RECOMMENDATION: PROCEED TO CONSENSUS PHASE

All three agents have legitimate needs. None are fundamentally at odds. Key conflicts are *solvable through design* (toggles, progressive disclosure, context-awareness).

**Next steps**:
1. Identify remaining conflicts (answer 5 questions above)
2. Seek unanimous consensus on each
3. Document final decisions in `CONSENSUS-DECISIONS.md`
4. Merge roadmap and hand off to design + engineering

---

## METRICS FOR SUCCESS (After Implementation)

- **Casual users**: Onboarding completion rate > 80% (A priorities)
- **Power users**: % jobs completed via keyboard > 50% (B priorities)
- **All users**: 2-week retention rate > 60% (C priorities, urgency messaging)
- **Accessibility**: WCAG 2.1 AA compliance (C baseline)

---

**Status**: All three agents ready for consensus phase.
**Estimated Timeline**: 2-3 weeks (foundation) + 2-3 weeks (power user) = 4-6 weeks to ship Tier 1 & 2

