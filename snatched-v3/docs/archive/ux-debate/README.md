# Snatched v3 UX Debate — Round 1: Agent Perspectives

**Status**: Round 1 Complete (Agent B: Power User Champion)
**Date**: 2026-02-24
**Format**: Three-agent debate structure with dedicated persona files

---

## Overview

This directory contains the UX debate framework for **Snatched v3**, a web app for recovering and organizing metadata from Snapchat data exports. Three agents will take turns advocating for different user personas and priorities, with final consensus decisions applied to the product.

---

## Agent Assignments

| Agent | Persona | Values | File |
|-------|---------|--------|------|
| **Agent A** | Casual User / Beginner | Simplicity, guidance, minimal cognitive load | `AGENT-A-CASUAL-USER-STORIES.md` (TBD) |
| **Agent B** | Power User Champion | Efficiency, control, keyboard shortcuts, batch ops, automation | `AGENT-B-POWER-USER-STORIES.md` ✅ COMPLETE |
| **Agent C** | Accessibility & Inclusive Design | WCAG 2.1, diverse abilities, internalization, neurodiversity | `AGENT-C-ACCESSIBILITY-STORIES.md` (TBD) |

---

## Current State: Agent B's Contributions

**Agent B** (Power User Champion) has completed **20 user experience stories** organized by priority:

### P0 (Critical) — 3 Stories
1. **Dashboard as Command Center** — Collapse results/download navigation into dashboard quick-actions
2. **Keyboard-First Navigation** — Global shortcuts (U/J/D/R/C, etc.) for every major action
3. **One-Click Download from Dashboard** — Skip Results page, download directly from job card

### P1 (High) — 2 Stories
4. **Batch Operations** — Multi-select jobs with bulk reprocess/download/delete
5. **Correction Workflow as Pipeline** — GPS → Timestamps → Redact → Match Config as seamless wizard, not islands

### P2 (Medium) — 8 Stories
6. **Upload Presets** — Save and reuse configurations (phases, lanes, EXIF options)
7. **Job Groups** — Group related uploads (trip, person, project) with aggregate stats
8. **Advanced Match Configuration** — Tweak strategy weights and thresholds without re-ingesting
9. **Data Density (Compact View)** — 100 rows/page, customizable columns, quick export
10. **Selective Reprocessing** — Re-run only specific phases/lanes without full re-ingestion
11. **Export Metadata** — JSON/CSV export of matches and assets for integrations
12. **Smart Filtering & Saved Searches** — Filter by confidence, strategy, date; save searches
13. **Webhooks & Automation** — Webhook triggers and scheduled reprocessing for downstream systems

### P3 (Nice-to-Have) — 7 Stories
14. **API Keys & Automation Visibility** — Quick-access cards on Dashboard for keys/webhooks/schedules
15. **Smart Dashboard Polling** — Faster refresh intervals, desktop notifications, jump-to-job overlay
16. **Correction History & Undo** — View correction timeline, undo specific changes
17. **Multi-Format Asset Download** — Bulk select and download assets; preview before download
18. **Tagging & Organization** — Tag jobs by person/context/year; filter Dashboard by tags
19. **Comparative Analysis** — View 3 jobs side-by-side comparing match confidence and stats
20. **Keyboard-Navigable Results Table** — Arrow keys, row jumps, virtual scrolling for 5,000+ rows

### Key Themes Across All Stories

**Workflow Efficiency** (Stories 1, 2, 5, 6, 11): Reduce clicks, keyboard navigation, context-switching
**Batch Processing** (Stories 3, 7, 16, 17): Multi-job and multi-asset operations at scale
**Customization & Reuse** (Stories 4, 10, 15, 18): Save configurations, presets, searches, tags
**Data Density** (Stories 10, 20): More info per page without cognitive overload
**Automation Integration** (Stories 9, 17): APIs, webhooks, exports for power user workflows
**Correction Pipeline** (Story 6): Transform isolated correction pages into coherent sequential wizard

---

## Story Format Used

Each story follows this structure:

```
### Story N: [Title]
**As a** [user type/persona]
**I want to** [action / feature]
**So that** [benefit / outcome]

**Current state**: [what exists today]
**Proposed fix**: [specific UX changes]
**Priority**: P0/P1/P2/P3
```

All stories reference **actual page names and routes** from the UI Design Spec (spec-08-web-app.md):
- `/upload` (upload page)
- `/dashboard` (job list)
- `/results/{job_id}` (summary/matches/assets tabs)
- `/download/{job_id}` (file tree)

---

## Next Steps: Round 2 & 3

### Round 2: Agent A (Casual User) — Expected Output
- ~15 stories focused on: guided workflows, onboarding, error prevention, clear language
- Emphasis on: one-path-to-success, hand-holding, progress indication, plain English copy
- Conflicts with Agent B: Will likely advocate for *hiding* advanced options and simplifying Dashboard

### Round 3: Agent C (Accessibility & Inclusion)
- ~15 stories focused on: WCAG 2.1 AA, keyboard navigation, screen readers, cognitive load, neurodiversity, internationalization
- Emphasis on: semantic HTML, high contrast, focus management, multiple modalities
- Conflicts: May require Agent B's compact view to scale to 100+ rows while maintaining readability

### Consensus Decisions (Final)
After all three agents submit, the team will:
1. Identify conflicts between personas
2. Seek unanimous consensus through negotiation
3. Document final UX decisions in `CONSENSUS-DECISIONS.md`
4. Create a merged prioritized roadmap

---

## Useful References

- **UI Design Spec**: `/docs/design/ui-design-spec.md` (7 screens, components, accessibility baseline)
- **Web App Spec**: `/docs/build-specs/spec-08-web-app.md` (FastAPI routes, pages, API endpoints)
- **Snatched v3 Overview**: `/docs/build-specs/spec-00-overview.md`
- **Architecture**: `/docs/planning/` (feature tree, phase roadmap)

---

## Key Design Constraints

1. **Tech Stack**: FastAPI + Jinja2 + htmx + Pico CSS (dark theme, no CSS-in-JS)
2. **Tier System**: Free / Pro / Team / Unlimited with feature gates
3. **Auth**: Authelia (header-based, no manual login code)
4. **Accessibility**: WCAG 2.1 AA minimum (already in spec)
5. **Responsiveness**: Mobile (< 768px) | Tablet (768-1024px) | Desktop (1024px+)
6. **Performance**: No external fonts, virtual scrolling for large tables, SSE for job progress

---

## How to Use This Repository

**For Agents** (Round 2 & 3):
1. Read `AGENT-B-POWER-USER-STORIES.md` for format and baseline
2. Create your persona file: `AGENT-A-CASUAL-USER-STORIES.md` or `AGENT-C-ACCESSIBILITY-STORIES.md`
3. Write 15-20 stories following the same format
4. Flag conflicts with Agent B stories (note them in your file)

**For Team Lead** (Consensus):
1. Read all three agent files
2. Identify conflicting recommendations (e.g., Story 10 "compact mode" vs. "large touch targets")
3. Facilitate discussion and seek unanimous consensus
4. Document final decisions in a **Consensus Table** showing how each conflict was resolved
5. Merge into prioritized roadmap

**For Designers/PMs**:
1. Use completed stories as user research input
2. Reference for wireframing and hi-fi mockups
3. Prioritize backlog based on final consensus decisions

---

## Metrics for Success

After implementation, measure:
- **Keyboard users**: % jobs completed via keyboard vs. mouse
- **Power users**: % time spent on Dashboard vs. Results page
- **Batch operations**: % of bulk operations used per month
- **Automation**: # webhook integrations active, # API calls per day
- **Error recovery**: % corrections without full re-processing
- **Retention**: Power users returning after 2+ weeks (compare Agent B vs. Agent A)

---

## Questions for Next Rounds?

- How should Agent A handle "admin" users managing team accounts (overlaps with Agent B's team features)?
- Should Job Groups (Story 7) and Tagging (Story 18) both exist, or consolidate?
- How much space on Dashboard is available before it becomes a "Cockpit" instead of "Command Center"?
- Keyboard shortcuts: Global or page-specific? (Agent C may advocate for consistent schema)

---

**Round 1 Status**: ✅ Agent B Complete (Power User Champion, 20 stories)
**Round 2 Status**: ✅ Agent A Complete (New User Advocate, 20 baseline + 3 new stories)
**Round 2 Additions**:
  - Agent A wrote comprehensive response with 5-8 agreements, 5-8 concerns, revised priorities (Top 15), and 3 new stories
  - All conflicts resolved with timing-based compromise (Phase 1: new users, Phase 2: power users, Phase 3: advanced)
  - Consensus Matrix created (12 major conflicts, decision rules applied)

**Expected Round 3**: Agent C (Product Strategist) — ✅ Complete (20 stories already submitted)
**Consensus Discussion**: 2026-02-26 (48 hours)
**Final Roadmap**: 2026-03-01 (ready for sprint planning)

**Key Deliverables (Round 2)**:
1. `AGENT-A-ROUND-2-RESPONSE.md` — Comprehensive analysis with conflicts and compromises
2. `ROUND-2-SUMMARY.md` — Executive summary with conflict resolution table
3. `ALL-60-STORIES-INDEX.md` — Master reference of all 60 stories from 3 agents
4. `CONSENSUS-MATRIX.md` — Decision table for 12 major conflicts with decision rules applied
