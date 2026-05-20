# Hotfix-9a Execution Notes

**Branch:** `sprint-9a` (cut off `sprint-8` 2026-05-19 — inherits H8 close-out PLANNING commits + new Jade/Inquisitor work)
**Executor:** Claude Opus 4.7 (Chris co-driving). Jade originally assigned to T1 but Chris re-assigned to Claude per the openclaw-cost gotcha (this session is subscription-billed; openclaw-dispatched sessions are not).
**Per:** Hotfix 9a draft by Jade (v2, Inquisitor pre-audit `approved-with-modifications` M1-M6 incorporated). Original combined Hotfix 9 was REJECTED on re-audit; H9a is the Tailwind-CDN-only slice.
**Inquisitor post-audit:** PENDING — Chris to dispatch.
**Deploy:** `266af25..8ffbc10` pushed to `origin/master` 2026-05-19 ~11:29 local. Render auto-deploy completed 11:30. CSS 404 detected → dashboard buildCommand manually updated → redeploy at 11:45 → live and verified.

---

## Completed: 2026-05-19

## Scope reality vs. plan

| Task | Status | Notes |
|---|---|---|
| T1 (class audit + safelist) | ✅ done | `PLANNING/research/class-audit.md`. 6 unique JS-manipulated classes from `index.html` (all in classList.add/remove). Zero className= assignments, zero Jinja-expression class values. |
| T2 (build pipeline) | ✅ done | `package.json`, `tailwind.config.js`, `static/css/input.css`, `render.yaml`, `.gitignore`, `DEPLOYMENT.md §8.5`. tailwindcss@3.4.17 pinned. Local `npm run build:css` produces 21K minified `output.css` in ~300ms. |
| T3 (replace CDN + remove from CSP) | ✅ done | 15 page templates patched. `app.py` CSP `script-src` reduced 4→3 entries. `unsafe-inline` retained (H10 scope). |
| T4 (visual regression) | ✅ done | Chris confirmed local 375px + Network tab. Page weight 50KB vs prior ~450KB (9× reduction). No regressions. |
| T5 (full regression) | ✅ done | pytest 84/18 (vs H8 66/36 — net -18 failures, zero new). Live CSP verified via curl. End-to-end quote flow on live produced expected $264.18 in both Quote #Q-000002 and Invoice #INV-000002 PDFs. |

## Three-bullet summary

- **What was done:** Replaced Tailwind CDN with a compiled-at-build-time `static/css/output.css` (21KB minified vs ~400KB runtime JS). Removed `cdn.tailwindcss.com` from CSP `script-src`. Set up the full Node build pipeline (package.json, tailwind.config.js, input.css) with content paths scanning templates + future static/js/, safelist derived from a one-pass class audit, build:css and dev:css npm scripts. Added DEPLOYMENT.md §8.5 documenting the asset pipeline for future operators. Verified end-to-end on live with a quote-generation test producing exact expected math.
- **What was deferred:** `unsafe-inline` removal in CSP (Hotfix 10 — requires externalizing 4 inline `<script>` blocks in `index.html` first). `style-src` `'unsafe-inline'` removal (out of scope — needs nonce/hash for the inline `<style>` font-family blocks). Bug 5 mobile nav drawer (Hotfix 9b). render.yaml Blueprint conversion (existing Render service ignored the new YAML — see surprises). Bug 1 AC3 (404/500 visual verification) — still carried over from H8.
- **What surprised:** (1) **`render.yaml` was ignored.** I assumed Render would auto-detect the YAML in the repo and apply the new buildCommand. Existing services don't auto-switch to Blueprint config — the dashboard buildCommand stays sticky. First deploy went live but `/static/css/output.css` returned 404 because only `pip install -r requirements.txt` ran. Chris manually edited the dashboard buildCommand to chain in `&& npm install && npm run build:css`, triggered a manual redeploy, and the second deploy worked. render.yaml is still in the repo as documentation + Blueprint-ready config for any future fresh service. (2) **pytest count moved from 66/36 to 84/18 — improvement, not a sprint artifact.** When I ran `pip install -r requirements.txt` earlier this session to fix a missing `flask_wtf` import for local Flask, dep versions shifted slightly and 18 of H8's pre-existing failures (mostly Stripe webhook mocks) resolved. The remaining 18 failures are a subset of H8's set — no new failures from this sprint. (3) **A11y label-association warnings on quote and account pages** surfaced when Chris opened DevTools "Issues" panel during live verification — 20 on quote, 5 on account. Pre-existing, not introduced here, but worth a future small sprint.

## Deploy timeline

| Time (local 2026-05-19) | Event |
|---|---|
| 11:29 | `git push origin master` (8ffbc10) |
| 11:30 | Render auto-deploy live — `/static/css/output.css` returns 404, build log shows only `pip install` ran |
| 11:39 | Diagnosed: render.yaml not honored by existing service |
| 11:45 | Chris updated Render dashboard buildCommand: `pip install -r requirements.txt && npm install && npm run build:css`, manual redeploy |
| 11:48 | Redeploy live, `/static/css/output.css` returns 200 with 21128 bytes |
| 11:50+ | Chris verified CSP header, console (no violations), and ran end-to-end quote flow → $264.18 matches expected |
