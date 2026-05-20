---
sprint: 9b
project: window-quoting
drafted_by: Jade
research_refs: []
content_refs: []
audited_by: Inquisitor
audit_status: approved
status: draft
created: 2026-05-19
revised: 2026-05-19 (v3 — logo integration task T3 added)
phase: Stabilize
---

# Hotfix 9b — Mobile Nav Overflow + Logo Integration

*Split from Hotfix 9 per Inquisitor re-audit. v2 incorporated advisory R1/R2. v3 adds T3 (logo integration — Fiverr commission received). Depends on Hotfix 9a completion (compiled CSS must exist).*

---

## Current State

### Bug 5. Mobile Nav Bar Overflow

On viewports <768px, the nav bar wraps to 3 rows consuming ~30% of viewport height. 7+ nav items don't fit in a single row at mobile widths.

**Solution:** Hamburger menu + slide-out drawer (right side, 80% width). Standard Material Design pattern.

---

## Tasks

- [ ] **T1: Hamburger + drawer implementation**
  - touches: `templates/_nav.html`, `static/js/nav.js`
  - assignee: Claude
  - acceptance:
    1. At <768px: nav items hidden, hamburger icon visible in single-row nav bar
    2. Hamburger tap opens slide-out drawer (right side, 80% viewport width) containing all nav items with ≥44px tap targets
    3. Drawer closes on: outside-tap (semi-transparent `bg-black/50` overlay), nav link click, Escape key
    4. At ≥768px: nav unchanged from current behavior (no hamburger, no drawer)
    5. All drawer JS in externalized `static/js/nav.js` (survives CSP — no inline script)
    6. All new Tailwind classes present in compiled `output.css`: `md:hidden`, `md:flex`, `hidden`, `translate-x-full`, `translate-x-0`, `transition-transform`, `duration-300`, `ease-in-out`, `fixed`, `inset-y-0`, `right-0`, `w-4/5`, `z-50`, `overflow-y-auto`, `bg-black/50` — verified by `grep` for each class in `static/css/output.css`. Note: this is a minimum list; Claude must verify ALL newly-introduced classes in `_nav.html` appear in compiled CSS, not just the enumerated ones.
    7. Semi-transparent overlay (`bg-black/50`) renders behind drawer when open
    8. Drawer self-tested on real Android device by Chris (informal verification during development; formal QA in T2)

- [ ] **T3: Logo integration**
  - touches: `templates/_nav.html`, `static/images/logo.*`, `static/css/output.css`
  - assignee: Claude
  - acceptance:
    1. Fiverr logo file placed in `static/images/` (SVG preferred, PNG fallback at 2x resolution)
    2. Logo displays in nav bar next to brand name on desktop (≥768px)
    3. Logo displays in hamburger nav bar on mobile (<768px) — may be icon-only at small widths
    4. Logo in drawer header above nav links
    5. Logo links to home page (`/`)
    6. `alt` text set to brand name for accessibility
    7. Logo file size <50KB (optimize if needed)

- [ ] **T2: Mobile nav + logo QA**
  - touches: none (QA only)
  - assignee: Chris
  - acceptance:
    1. No CSP violations in browser console related to `nav.js`
    2. `static/js/nav.js` loads with HTTP 200
    3. Visual correct at 320px, 375px, 414px (mobile) and 768px, 1280px (desktop)
    4. No nav-related layout shifts or CLS issues
    5. Real Android device test: drawer opens, closes, navigates correctly
    6. Semi-transparent overlay renders correctly on mobile
    7. Logo displays correctly at all breakpoints, links to home, accessible alt text present

---

**Sprint type:** Stabilize (UX fix)
**Estimated complexity:** S (single component, externalized JS)
**Rollback:** Remove hamburger/drawer markup from `_nav.html`, delete `nav.js`, restore flex-wrap behavior.

**Dependency:** Hotfix 9a must be complete (compiled CSS with all required classes available).

**Explicit non-scope:**
- Tailwind CDN migration (HF9a)
- `unsafe-inline` removal (HF10)

**Prerequisite:** Chris provides logo file (Fiverr commission — received 2026-05-19). Drop into `projects/window-quoting/static/images/` before Claude starts T3.