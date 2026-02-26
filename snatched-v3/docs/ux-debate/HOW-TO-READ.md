# How to Read Agent B's Stories — A Quick Guide

**Total Stories**: 20 (grouped by priority P0-P3)
**Total Word Count**: ~15,000 words across 3 files
**Time to Read**: 45-60 minutes (cover-to-cover) | 15-20 minutes (summary + priority table)

---

## Files in This Directory

| File | Purpose | Length | Read Time |
|------|---------|--------|-----------|
| `AGENT-B-POWER-USER-STORIES.md` | Full story details with acceptance criteria | 521 lines | 30 min |
| `AGENT-B-SUMMARY.md` | Index, priority grid, conflicts, roadmap | 291 lines | 20 min |
| `README.md` | Debate framework, next steps, metrics | 179 lines | 10 min |
| `HOW-TO-READ.md` | This file — navigation guide | | 5 min |

---

## Quick Navigation

### I'm in a Hurry (5 minutes)
1. Read: `AGENT-B-SUMMARY.md` → **Story Index** table (20 stories, effort/impact)
2. Glance: **Priority Distribution** chart (P0/P1/P2/P3 breakdown)
3. Check: **Key Conflicts with Agent A** (what to expect in Round 2)

### I Want the Big Picture (15 minutes)
1. Read: `AGENT-B-SUMMARY.md` → Full file (index, themes, conflicts)
2. Skim: `README.md` → Overview + next steps
3. Result: You understand Agent B's philosophy and where they'll conflict with other personas

### I Need Implementation Details (45 minutes)
1. Read: `AGENT-B-SUMMARY.md` → Full
2. Read: `AGENT-B-POWER-USER-STORIES.md` → Full (all 20 stories with current state + proposed fixes)
3. Reference: `README.md` for story format and design constraints

### I'm Designing/Building (60 minutes)
1. Read: `AGENT-B-POWER-USER-STORIES.md` → Full (implementation-ready details)
2. Extract: Page routes (e.g., `/dashboard`, `/corrections/{job_id}`) and API endpoints (e.g., `POST /api/jobs/{job_id}/reprocess`)
3. Check: `AGENT-B-SUMMARY.md` → **Implementation Roadmap** to see suggested sprint plan
4. Start: With P0 stories (3 critical, 2 foundational)

---

## Story Format Explained

Every story follows this template:

```
### Story N: [Title]
**As a** [user type]
**I want to** [action/feature]
**So that** [benefit/outcome]

**Current state**: [what exists in the spec or current codebase]
**Proposed fix**: [specific UX changes with details]
**Priority**: P0/P1/P2/P3
```

### Example: Story 1 (Dashboard as Command Center)

```
### Story 1: Dashboard as Command Center
**As a** data hoarder managing 20+ Snapchat exports annually
**I want to** see job status, latest results, and next actions in a single view without navigation fatigue
**So that** I can stay in control and unblock myself quickly without clicking through results/download pages

**Current state**: Dashboard shows 3 stat cards and a list of job cards. Each job requires a "View Results" click to see summary; download is buried on a separate page.

**Proposed fix**:
- Add a compact 4th column to job cards (desktop): Quick stats badge showing "X matched / Y total | GPS: Z%"
- Add a "Download Latest" button on completed job cards (right-align, secondary style)
- Implement quick-action dropdown menu on each card (three dots): "View Results | Reprocess | Download | Delete"
- Show progress inline on running jobs: progress bar + "Phase 2/4 | 35%" instead of separate phase page
- Add a "Bulk Select" checkbox and a sticky footer action bar for batch operations (see Story 3)

**Priority**: P1 (high)
```

**What This Means**:
- The **"As a..."** clause defines who Agent B is speaking for (data hoarders, photographers, power users)
- The **"I want..."** is the feature or behavior change
- The **"So that..."** is the actual user outcome (faster workflow, less friction)
- The **"Current state"** references the UI Design Spec (spec-08-web-app.md) or existing app
- The **"Proposed fix"** is **specific and actionable** — a designer can wireframe from this
- The **"Priority"** P0-P3 signals importance relative to other power user stories

---

## Key Concepts

### The 8 Themes

Agent B groups stories into **8 core themes**. Understanding these helps see the big picture:

1. **Workflow Efficiency** (4 stories): Reduce clicks and keyboard navigation
   - Stories: 1, 2, 5, 20
   - Core: "Don't make me use the mouse. Don't make me navigate."

2. **Batch Processing** (4 stories): Multi-job and multi-asset operations
   - Stories: 3, 7, 16, 17
   - Core: "I have 20 exports. I need to bulk reprocess, not click 20 times."

3. **Customization & Reuse** (4 stories): Save preferences and templates
   - Stories: 4, 8, 15, 18
   - Core: "I do the same thing every month. Let me save it once."

4. **Data Density** (2 stories): Pack more info per page
   - Stories: 10, 20
   - Core: "Show me 5,000 rows with smart filtering, not 20 per page."

5. **Automation & Integration** (3 stories): APIs, webhooks, exports
   - Stories: 9, 13, 17
   - Core: "I build automations. Give me APIs and webhooks."

6. **Safety & Inspection** (2 stories): Reduce risk, enable rollback
   - Stories: 6, 14
   - Core: "Advanced features need guardrails. Let me undo mistakes."

7. **Analysis & Comparison** (2 stories): Insight and decision-making
   - Stories: 12, 19
   - Core: "Let me compare outcomes to optimize."

8. **Monitoring** (1 story): Real-time job status
   - Stories: 11
   - Core: "Tell me when my jobs complete."

**When designing, group features by theme.** For example, Stories 1 + 2 (Dashboard + Keyboard) should ship together to provide a cohesive "power user experience."

---

## How Stories Reference the App

All stories reference **actual pages and routes** from the web app spec:

### Pages (GET routes, return HTML)
- `/` — Landing page
- `/upload` — Upload form page
- `/dashboard` — Job list (main hub)
- `/results/{job_id}` — Results browser (3 tabs: Summary, Matches, Assets)
- `/download/{job_id}` — Download manager page
- `/settings/*` — Settings ecosystem (future, post-MVP)

### API Endpoints (JSON, no auth required in examples)
- `POST /api/upload` — Accept ZIP file
- `GET /api/jobs` — List jobs
- `GET /api/jobs/{job_id}` — Job details
- `GET /api/jobs/{job_id}/stream` — SSE progress stream
- `POST /api/jobs/{job_id}/cancel` — Cancel a job
- `POST /api/jobs/{job_id}/reprocess` — Trigger reprocessing

### New Routes Proposed in Stories

**Story 1 & 5**: Single-page download (already on /download/{job_id})
**Story 4**: `GET /api/presets` — List upload presets
**Story 6**: `GET /corrections/{job_id}` — Correction wizard page
**Story 8**: `GET /results/{job_id}/match-config` — Match configuration modal/page
**Story 9**: Dashboard card quick-linking to `GET /settings/api-keys`, `GET /settings/webhooks`
**Story 12**: `POST /api/jobs/{job_id}/reprocess` with phase/lane filtering
**Story 13**: `GET /api/jobs/{job_id}/export?format=json|csv&type=matches|assets`
**Story 14**: `GET /results/{job_id}/history` + `POST /api/jobs/{job_id}/corrections/{correction_id}/undo`
**Story 15**: `GET /api/jobs/{job_id}/matches?filter={"confidence": [50, 60]}` + saved search storage
**Story 16**: `POST /api/jobs/{job_id}/assets/download` (bulk asset download)
**Story 17**: `POST /api/webhooks`, `GET /api/schedules`
**Story 18**: `PATCH /api/jobs/{job_id}/tags`
**Story 19**: `GET /api/compare?jobs=123,124,125`

---

## Priority Levels Explained

### P0 — Critical Path (Must Have for Power Users)
**3 stories**: Dashboard command center, keyboard shortcuts, one-click download
**Ship Together**: Yes. These define the power user experience baseline.
**Timeline**: Sprint 1
**Why**: Without these, power users will feel "slowed down" by the web UI vs. command-line.

### P1 — Foundational (Unblocks Other Features)
**2 stories**: Batch operations infrastructure, correction pipeline
**Ship Together**: Somewhat. Batch ops enable Stories 7, 16, 17. Correction pipeline is independent.
**Timeline**: Sprint 1-2
**Why**: Batch ops is infrastructure; many P2 features depend on it. Correction pipeline is the power user's core workflow.

### P2 — Power User Phase (The Meat of the Feature Set)
**8 stories**: Presets, job groups, match config, compact view, selective reprocess, export formats, smart filters, webhooks
**Ship Together**: No. Organized into Sprints 2-4 based on dependencies.
**Timeline**: Sprint 2-5
**Why**: These are what power users actually ask for. They unlock productivity.

### P3 — Polish & Nice-to-Have (Delight Users)
**7 stories**: API visibility, fast polling, correction history, asset bulk download, tagging, comparison, table keyboard nav
**Ship Together**: No. These are independent quality-of-life improvements.
**Timeline**: Sprint 5-6 (or later, if time runs out)
**Why**: If P0-P2 are shipped, power users are happy. P3 is "chef's kiss" polish.

---

## Conflicts with Other Agents (Sneak Peek)

### Agent A (Casual User) Will Likely Say...

Agent A advocates for **simplicity, guidance, and linear workflows**. They'll conflict with Agent B on:

| Story | Agent B | Agent A Likely Counter |
|-------|---------|------------------------|
| 1 (Dashboard) | Rich info, quick menus | Too much info; overwhelm |
| 2 (Keyboard) | Single-key shortcuts (U, J, D) | Discoverable only, no single letters |
| 3 (Batch Ops) | Multi-select, bulk reprocess | One job at a time, guided |
| 6 (Correction Pipeline) | 4-step wizard, all options | Single form with guidance |
| 10 (Compact View) | 100 rows, small font | 15 rows, large touch targets |

**Likely Resolution**: "Expert Mode" toggle or beginner/power user dashboard variants.

### Agent C (Accessibility) Will Likely Say...

Agent C advocates for **universal design, WCAG 2.1 AA compliance, neurodiversity, internationalization**. They'll conflict with Agent B on:

| Story | Agent B | Agent C Likely Counter |
|-------|---------|------------------------|
| 2 (Keyboard Shortcuts) | Single letters (U, D, J, ?) | Collisions, no Cmd/Ctrl, discoverable? |
| 10 (Compact View) | 100 rows, 0.875rem font | Violates contrast + readability |
| 20 (Table Nav) | Arrow keys, Ctrl+G jumps | Screen reader support, focus management |
| 6 (Pipeline) | Visual step indicator | Step text required, progress announced |
| 3 (Checkboxes) | Small, visual-only | 44px touch targets, accessible labels |

**Likely Resolution**: Separate keyboard shortcut schemes (configurable), responsive design scales font/density by screen size, full ARIA roles.

---

## How to Use This for Roadmap Planning

### Step 1: Identify MVP (P0 + P1)
- Story 1: Dashboard redesign
- Story 2: Keyboard shortcuts
- Story 5: One-click download
- Story 3: Batch operations (infrastructure)
- Story 6: Correction wizard

**Effort**: 2-3 sprints
**Benefit**: Power users feel the app is built for them

### Step 2: Add Power User Phase (P2 early)
- Story 4: Upload presets (popular request)
- Story 10: Compact view (data density)
- Story 15: Smart filtering (find issues fast)
- Story 8: Advanced match config (transparency)

**Effort**: 2-3 sprints
**Benefit**: Productivity features, team/pro differentiation

### Step 3: Batch + Integration (P2 late)
- Story 7: Job groups (team tier)
- Story 16: Asset bulk download
- Story 17: Webhooks & automation
- Story 13: Export formats

**Effort**: 2 sprints
**Benefit**: Scale and automation; Zapier integrations unlock

### Step 4: Polish (P3)
- Everything else

**Effort**: 1-2 sprints (optional)
**Benefit**: Delight, not necessity

---

## Questions to Ask While Reading

### For Product Managers
- Which stories directly increase revenue (unlock pro/team tier features)?
- Which stories reduce support burden (self-service corrections, undo)?
- Which stories unlock integrations (webhooks, APIs)?
- Which stories are "table stakes" for competing products?

### For Designers
- Which stories introduce new page routes (coordination needed)?
- Which stories require new database tables (schema design)?
- Which stories have tight keyboard navigation requirements (special case)?
- Which stories scale to 5,000+ rows (performance, virtual scrolling)?

### For Developers
- Which stories require API changes (new endpoints, request/response schema)?
- Which stories introduce async/background processing (webhooks, schedules)?
- Which stories touch authentication/authorization (tier checks, group management)?
- Which stories introduce new dependencies (libraries, external services)?

### For Accessibility
- Do all keyboard-navigable features have visible focus states?
- Are color-coded indicators (e.g., confidence %) backed by text/icons?
- Are modal overlays (e.g., filter picker) keyboard-closable (Escape)?
- Are live data updates announced to screen readers (aria-live)?

---

## Next Steps After Reading

1. **Skim** Agent B's summary for 5 minutes
2. **Share** with team; ask "What's missing? What do you disagree with?"
3. **Wait** for Agent A (Casual User) and Agent C (Accessibility) to submit their stories
4. **Compare** all three sets and identify conflicts
5. **Debate** conflicts; seek unanimous consensus
6. **Document** final decisions in a Consensus Table
7. **Prioritize** the merged roadmap
8. **Design** wireframes based on P0/P1 stories first

---

## Glossary

| Term | Definition |
|------|-----------|
| **Persona** | A user archetype (e.g., "photographer with 10,000 photos") |
| **User Story** | A feature described from a user's perspective: "As a X, I want Y so that Z" |
| **Current State** | What the UI/app does today (from spec or existing code) |
| **Proposed Fix** | The specific UX change suggested by the agent |
| **Priority** | P0 (critical) to P3 (nice-to-have) |
| **Theme** | A grouping of related stories (e.g., "Batch Processing") |
| **Conflict** | A disagreement between agents about trade-offs |
| **Consensus** | A decision agreed upon by all three agents (goal of the debate) |
| **Effort** | Estimated sprint effort: L (1-2 days), M (3-5 days), H (1+ sprints) |
| **Impact** | Expected user benefit: HIGH (differentiation), MEDIUM (nice-to-have), LOW (polish) |

---

## Final Notes

- **Stories are opinionated**. Agent B is a "power user champion," not a balanced product manager. That's the point.
- **Stories are actionable**. Each one includes specific page routes, API endpoints, and acceptance criteria.
- **Stories will be debated**. Agent A will push for simplicity, Agent C for accessibility. Healthy conflict leads to better design.
- **Expect ~30% of stories to be marked P3 or deferred**. That's normal; the real value is in P0-P2.
- **Read with your team**. The stories are a conversation starter, not the final spec.

Questions? Open `/docs/ux-debate/README.md` to see the debate framework and what to expect in Rounds 2 and 3.

Happy reading!
