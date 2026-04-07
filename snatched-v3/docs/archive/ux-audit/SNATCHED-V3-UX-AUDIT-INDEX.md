# Snatched v3 UX Audit — Complete Index
**2026-02-26 | Gravity-style analysis of real user experience**

---

## Documents in This Audit

This audit consists of **5 detailed documents** analyzing Snatched v3 from the perspective of a real first-time user. Read in this order:

### 1. **SNATCHED-V3-UX-AUDIT-SUMMARY.md** ← START HERE
**Executive summary. 5-10 minute read.**
- Overall verdict: B+ product with A- bones.
- Three levels of assessment (Functional, Visual, Emotional).
- Biggest gaps and quick wins.
- Recommended work plan (3 phases).

### 2. **snatched-v3-ux-audit.md**
**Deep dive. 20-30 minute read.**
- Page-by-page analysis: Login, Upload, Dashboard, Job, Results, Download.
- What works well, what's rough, why it matters.
- Quick-win vs rebuild recommendations.
- Global CSS issues across all pages.

### 3. **snatched-v3-ux-fixes-checklist.md**
**Implementation guide. Reference while coding.**
- 3 sprints of fixes (Quick Wins, Medium Effort, Polish).
- Code snippets for every fix.
- Testing instructions.
- Prioritized by time and impact.

### 4. **snatched-v3-emotional-beats-analysis.md**
**Spec vs Reality. 15-20 minute read.**
- Compares the spec's 5 "holy shit" moments to what actually exists.
- Scores each beat (0-10).
- Explains why some deliver, why some don't.
- Shows emotional arc delivery rate: 3.4/10.

### 5. **snatched-v3-ux-visual-reference.md**
**Component inventory. Reference as needed.**
- ASCII mockups of each page.
- Component maturity scores.
- Color palette and animation audit.
- Responsive breakpoint analysis.

---

## Quick Navigation

### For Product Managers / Designers
1. Read **SNATCHED-V3-UX-AUDIT-SUMMARY.md** (5 min).
2. Skim **snatched-v3-emotional-beats-analysis.md** (10 min).
3. Reference **snatched-v3-ux-visual-reference.md** as needed for mockups.

Result: You'll understand the gap between vision and execution, and the priority fixes.

### For Developers
1. Read **SNATCHED-V3-UX-AUDIT-SUMMARY.md** (5 min) for context.
2. Go straight to **snatched-v3-ux-fixes-checklist.md** for implementation.
3. Reference **snatched-v3-ux-audit.md** for detailed reasoning on each fix.

Result: You'll have code snippets, testing instructions, and priorities.

### For Dave (Architecture Review)
1. Read **SNATCHED-V3-UX-AUDIT-SUMMARY.md** (5 min).
2. Read **snatched-v3-emotional-beats-analysis.md** to see why spec delivery is at 3.4/10.
3. Scan **snatched-v3-ux-audit.md** for "Rebuild?" verdicts.

Result: You'll know what's foundational (keep) vs what needs rework (density band, export viz).

---

## Key Findings at a Glance

### The Good
- All pages render without errors.
- Gallery populates with photos in chronological order (EMOTIONAL HIT).
- Map renders with GPS pins.
- Job pipeline flows correctly.
- Tools are accessible to power users.
- Dark rebellion theme is applied consistently.
- Form validation works.

### The Rough
- Form focus states are generic (browser blue, not snap-yellow).
- Loading states are missing (empty grids, no spinners).
- Mobile layouts exist but aren't fully responsive.
- Disabled elements don't look disabled.
- Countdown modal might not fit on mobile with config panel.

### The Missing
- Data viz band (file-type colors, duplicate density) — CRITICAL.
- GPS pins blooming in real-time (they appear all at once).
- Export phase visualization (no thumbnail updates).
- Rescue count is not prominent on download page.
- Password reset link on login page.

### Emotional Delivery Breakdown
- Beat 1 (Gallery): 6/10 — Works, but experience is flat.
- Beat 2 (Map): 5/10 — Works, but not real-time.
- Beat 3 (Export viz): 2/10 — Not implemented.
- Beat 4 (Date range): 4/10 — Works, but quiet.
- Beat 5 (Density band): 0/10 — Not implemented.
- **Overall**: 3.4/10 (vs spec's aspirational 10/10).

---

## Work Plan Summary

### Phase 1: Quick Wins (1 hour)
- Form focus states (5 min)
- Download hero count (10 min)
- Login error styling (5 min)
- Drag zone border (8 min)
- Disabled tool styling (5 min)

Impact: User feels form is branded, interactive elements are clear, final experience is celebratory.

### Phase 2: Polish (4-6 hours)
- Dashboard loading spinner (1 hr)
- Countdown modal mobile (30 min)
- Tools sidebar mobile drawer (2 hrs)
- Results page consolidation (20 min)

Impact: Mobile experience is smooth, loading feedback is clear, no confusion.

### Phase 3: Spec Fulfillment (6-10 hours)
- Data viz band with segments and density (6-8 hrs)
- GPS live-stream during Enrich (2-4 hrs)
- Export file visualization (4-6 hrs)

Impact: All 5 emotional beats from spec are delivered.

---

## Files and Line Numbers

### User Journey Files

| Page | File | Key Class | Issues |
|------|------|-----------|--------|
| Login | `login.html` (47 lines) | `.auth-form` | No password reset, focus states generic |
| Upload | `upload.html` (100+ lines) | `.upload-zone` | Drag zone visual feedback weak |
| Dashboard | `dashboard.html` (134 lines) | `.job-card` | No loading spinner |
| Job (Main) | `job.html` (470 lines) | `.viz-band` | Density band missing |
| Results | `results.html` (372 lines) | `.tab-nav` | Redundant reports, confusing labels |
| Download | `download.html` (96 lines) | `.download-card` | Rescue count not prominent |

### CSS
- File: `/home/dave/CascadeProjects/snatched-v3/snatched/static/style.css` (47,748 tokens)
- Key sections: buttons (394-480), nav (261-320), components (524-2300), responsive (1902-5569)
- Issues: Missing spinners, inconsistent hover states, form focus not themed, mobile gaps

---

## Metrics Summary

| Metric | Score | Interpretation |
|--------|-------|-----------------|
| Functional completeness | 9/10 | All core flows work, no blockers |
| Visual polish | 6/10 | Theme applied, but missing animations and focus states |
| Emotional delivery | 3.4/10 | Spec promised 5 moments; ~2 are delivered |
| Responsive readiness | 6/10 | Breakpoints exist, but not fully tested |
| Accessibility | 7/10 | Forms work, nav is clear, but no ARIA labels |
| Overall maturity | 6.8/10 | Solid foundation, needs polish |

---

## File Locations

All audit documents in `/home/dave/docs/`:

```
SNATCHED-V3-UX-AUDIT-INDEX.md           ← You are here
SNATCHED-V3-UX-AUDIT-SUMMARY.md         ← Start here
snatched-v3-ux-audit.md                 ← Deep dive
snatched-v3-ux-fixes-checklist.md       ← Implementation guide
snatched-v3-emotional-beats-analysis.md ← Spec alignment
snatched-v3-ux-visual-reference.md      ← Component inventory
```

Snatched codebase at `/home/dave/CascadeProjects/snatched-v3/snatched/`:

```
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── upload.html
│   ├── dashboard.html
│   ├── job.html (main experience)
│   ├── results.html
│   └── download.html
├── static/
│   ├── style.css (all styling)
│   └── htmx.min.js
└── api.py (8,935 lines)
```

---

## Next Steps

1. Read SNATCHED-V3-UX-AUDIT-SUMMARY.md (5 min).
2. Decide which phase to tackle (Quick Wins = highest ROI).
3. Open snatched-v3-ux-fixes-checklist.md and start with Phase 1.
4. Test on desktop (1920px), tablet (768px), mobile (480px).
5. Reference snatched-v3-ux-audit.md if you need reasoning on any fix.

---

**Audit complete. Ready to polish.**
