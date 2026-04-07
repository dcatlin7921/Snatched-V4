# Snatched v3 UX Audit — Executive Summary
**2026-02-26 | Gravity-style analysis of real user experience**

---

## The Verdict

**Snatched v3 is a B+ product with A- bones.**

A real user will:
1. ✓ Log in successfully (minor form polish needed)
2. ✓ Upload their Snapchat export (drag zone feedback missing)
3. ✓ Watch their job progress in real-time (data viz band is minimal)
4. ✓✓ See their photos in chronological order for the first time (EMOTIONAL HIT)
5. ✓ Discover their GPS travel history on a map (works, but not real-time)
6. ✓ Get files exported and ready to download (smooth experience)
7. ✓ Download their rescued memories (large zip, all working)

**But they'll also notice:**
- Form inputs don't feel branded (default blue focus rings, not snap-yellow)
- Loading states are missing (empty grids while htmx fetches, no spinner)
- The signature "archive density band" visual is completely absent
- Mobile experience is functional but not fully responsive
- The final "rescue count" moment is understated (should be bold and large)

**Bottom line: The experience works and the emotional core (seeing your photos) is there. But it needs 2-4 hours of CSS polish and 6-8 hours of feature completion to match the spec.**

---

## Three Levels of Assessment

### 1. FUNCTIONAL (Does it work?)
**Score: 9/10**

- All pages render without errors.
- Navigation is clear (3-link sidebar nav).
- Modals appear and dismiss correctly.
- Forms submit and validate.
- Job pipeline flows correctly (ingest → match → enrich → export).
- Gallery populates with thumbnails.
- Map renders with pins.
- Download works.

**Issues**: None blocking. All core flows are implemented.

---

### 2. VISUAL / POLISH (Does it look finished?)
**Score: 6/10**

- Dark rebellion theme is applied consistently (snap-yellow accents, caution tape, heart-broken icon).
- Typography is clean (Inter + JetBrains Mono).
- Layout is logical (top nav, main content, footer).
- Component styling is present for buttons, cards, forms.
- Responsive breakpoints exist for 768px and 480px.

**Issues**:
- Form focus states are generic (browser blue, not snap-yellow).
- No loading spinners anywhere (makes page feel slow on poor networks).
- Table rows don't highlight on hover (interaction feedback).
- Disabled elements don't look disabled (no opacity, cursor change).
- Some CSS transitions are missing (smooth animations).
- Mobile layouts exist but aren't fully tested.

---

### 3. EMOTIONAL / UX (Does it feel like a rescue?)
**Score: 4/10**

**The spec promised 5 "holy shit" moments:**

1. ✓ Gallery populates in date order → **WORKS, but experience is flat.** Thumbnails appear, user recognizes photos. But no animation, no counter showing "1,247 matched so far," no ceremony.

2. ✓ GPS pins bloom on the map → **PARTIAL.** Map renders with pins, user sees travel history. But pins appear all at once (when user clicks tab), not blooming in real-time as Enrich runs.

3. ✗ Real thumbnails replace placeholders → **NOT IMPLEMENTED.** No visual update during Export. User stares at progress bar; they don't see files materializing.

4. ~ Date range appears during Ingest → **WORKS BUT QUIET.** Stats row shows "Jan 2018 — Feb 2024" in small monospace text. Correct data, but no emotional emphasis.

5. ✗ Archive density band → **NOT IMPLEMENTED.** The signature visual feature (colored segments showing file types, darker saturation for duplicates) is completely missing. This is the biggest spec gap.

**Overall emotional delivery: 3.4/10.**

User gets their files and feels satisfaction. But they don't feel the "six years of your life, rescued in real-time" moment the spec promised.

---

## The Biggest Gaps

### 1. Data Viz Band (Critical)
**What spec says**: "Segmented bar fills left-to-right as files counted — segments colored by type (photos warm white, videos amber, chats steel blue, other muted grey). Duplicate density = darker saturation."

**What exists**: Plain phase labels + monospace stats + progress bar. No color segmentation. No density visualization.

**Why it matters**: This is the signature visual of the whole product. It's what makes the experience feel like "watching your archive get reconstructed" vs "uploading a file."

**Effort to implement**: 6-8 hours (requires backend to compute file-type breakdown and duplicate density).

---

### 2. Loading States (High Impact)
**What spec says**: Implicitly, user sees live updates as process runs.

**What exists**: Text "Loading..." with no animation. Empty grids while waiting for htmx. Page feels slow on poor networks.

**Why it matters**: User thinks page is broken or slow, not that it's loading.

**Effort to implement**: 1-2 hours (add universal spinner animation + wire to htmx events).

---

### 3. Form Focus States (Quick Win)
**What spec says**: Implicitly, everything should feel rebellion-themed.

**What exists**: Default browser blue/grey focus rings on input fields.

**Why it matters**: Breaks the visual consistency. Makes form feel generic, not branded.

**Effort to implement**: 5 minutes (CSS rule: `input:focus { border: 2px solid var(--snap-yellow); }`).

---

### 4. Export Phase Visualization (Medium Effort)
**What spec says**: "Real thumbnails replace placeholders during Export. Abstract data becomes your actual photos."

**What exists**: Progress bar only. No thumbnail updates during export.

**Why it matters**: User doesn't see files materializing. Export phase feels like waiting, not creating.

**Effort to implement**: 4-6 hours (requires backend to stream per-file progress, frontend to animate thumbnails).

---

### 5. Rescue Count Prominence (Quick Win)
**What spec says**: "Large count in snap-yellow: 4,847 files rescued."

**What exists**: Small stat card showing file count + size.

**Why it matters**: Download page is the emotional close. The count should be bold and celebratory, not tucked in a card.

**Effort to implement**: 10 minutes (move count to hero section, make text larger and snap-yellow).

---

## What's Actually Really Good

### 1. Job Page Flow ✓✓
The job.html template is **well-architected**. Single page with progressive state changes, view tabs that enable as data arrives, countdown modals that give user agency. The flow is elegant.

### 2. Gallery Experience ✓✓
When Match completes and gallery populates, user sees their actual Snapchat photos in chronological order. This is genuinely moving. It's the "aha!" moment of the whole app. **This works.**

### 3. Tools Access ✓
Power users can pause and access GPS correction, timestamp fixes, etc. The Tools sidebar has good structure (CORRECTIONS, EXPLORE, ORGANIZE, ACTIONS). Accessible and well-organized.

### 4. Dashboard Stats ✓
Processing slots visualization (dot indicators) + queue position is transparent and clear. User knows exactly where they are in the queue.

### 5. Results Aggregation ✓
After job completes, user can download reports (JSON/CSV) with detailed match data, asset inventory, phase timings. Good for power users.

---

## Quick Wins (1-2 hours for major polish)

**Do these FIRST. High ROI on user perception.**

1. **Form focus states** (5 min): Add snap-yellow border + box-shadow to `input:focus`.
2. **Drag zone border** (8 min): Add dashed snap-yellow border + background change on hover.
3. **Disabled tool styling** (5 min): Add opacity + cursor change to disabled tools.
4. **Download hero count** (10 min): Move rescue count to hero section, snap-yellow, 2rem font.
5. **Login error styling** (5 min): Add red border + background to error messages.

**Combined effort: ~33 minutes. Impact: User feels like form is branded, interactive elements are clear, final experience is celebratory.**

---

## Medium Effort (4-8 hours, high-medium impact)

1. **Dashboard loading spinner** (1 hr): Add htmx loading indicator.
2. **Countdown modal mobile** (30 min): Ensure modal + config panel fit on 480px.
3. **Tools sidebar mobile drawer** (2 hrs): Add hamburger toggle, slide-out drawer.
4. **Data viz band with segments** (6-8 hrs): Rebuild with colored file-type bars + density visualization.
5. **GPS live-stream** (2-4 hrs): Send GPS updates via SSE during Enrich, animate pins in real-time.

**Combined effort: 11.5-16.5 hours. Impact: Product feels premium, spec's emotional beats are delivered.**

---

## File Organization

I've created 4 companion audit documents:

1. **snatched-v3-ux-audit.md** (this directory)
   - Deep dive on each page/component.
   - What works, what's rough, why it matters.
   - Quick-win vs rebuild recommendations.

2. **snatched-v3-ux-fixes-checklist.md**
   - Step-by-step fix instructions with code snippets.
   - Organized by sprint (1-2 hours, 4-8 hours).
   - Testing instructions.

3. **snatched-v3-emotional-beats-analysis.md**
   - Compares spec's 5 "holy shit" moments to what actually exists.
   - Scores each beat 0-10.
   - Explains why some work, why some don't.

4. **snatched-v3-ux-visual-reference.md**
   - ASCII mockups of each page.
   - Component inventory with maturity scores.
   - Color palette and animation audit.

---

## Recommended Work Plan

### Phase 1: Quick Wins (Tomorrow, 1 hour)
- Form focus states
- Download hero count
- Login error styling
- Drag zone border
- Disabled tool visibility

**Before/after**: Form feels branded. Final moment is celebratory. Interactive elements are clear.

### Phase 2: Polish (This weekend, 4-6 hours)
- Dashboard loading spinner
- Countdown modal mobile
- Tools sidebar mobile drawer
- Results page consolidation

**Before/after**: Mobile experience is smooth. Loading feedback is clear. No confusion about where to find reports.

### Phase 3: Spec Fulfillment (Next week, 6-10 hours)
- Data viz band with segments + density
- GPS live-stream during Enrich
- Export phase file visualization

**Before/after**: All 5 emotional beats from spec are delivered. User feels like they're rescuing their archive in real-time.

---

## Risk Assessment

**What could go wrong?**

1. **Difficulty computing file-type breakdown**: If backend can't easily determine file types during ingest, density band is harder. **Mitigation**: Start with a simpler version (just photos vs videos), then add chat/other.

2. **GPS streaming overhead**: If SSE sends too many GPS events, it could overwhelm the connection. **Mitigation**: Batch GPS events (send 10 at a time) and throttle to 1 batch/second.

3. **Mobile layout regressions**: Adding new CSS might break existing mobile layouts. **Mitigation**: Test all breakpoints (480px, 768px) after each change.

4. **Export file-write streaming**: Depends on backend streaming capability. If not available, skip this feature. **Mitigation**: Use what works (progress bar) instead of chasing unachievable perfection.

---

## Success Criteria

**After all fixes:**

1. ✓ Form focus states are snap-yellow (not browser blue).
2. ✓ Loading spinners appear when htmx is fetching.
3. ✓ Rescue count is large and snap-yellow on download page.
4. ✓ Mobile layouts fit at 480px (no truncation or overflow).
5. ✓ Data viz band shows file-type colors and fills during ingest.
6. ✓ GPS pins appear live on map during Enrich (not all at once).
7. ✓ All disabled elements look disabled (opacity + cursor).
8. ✓ Countdown modal fits on mobile with export config visible.

**User perception**: "This is polished. The experience is smooth. I can see my archive being reconstructed in real-time."

---

## Final Thought

**Snatched v3's foundation is solid.** The architecture works. The emotional core (seeing your photos) is there. The vision is clear.

**What's missing is** the ceremony — the animations, the spinners, the dramatic moments that make it feel like a *rescue* and not just a *download*.

**This is fixable.** With focused work on the items above, Snatched goes from "a functional tool that works" to "a product that feels premium and delivers on its promise."

---

**Audit complete. All detailed recommendations and code snippets in companion files.**

**Questions? Check:**
- `snatched-v3-ux-fixes-checklist.md` for implementation steps.
- `snatched-v3-emotional-beats-analysis.md` for spec alignment details.
- `snatched-v3-ux-visual-reference.md` for component mockups.
