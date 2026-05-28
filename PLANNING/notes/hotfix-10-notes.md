# Hotfix-10 Execution Notes

**Branch:** `sprint-10` (cut off `master` 2026-05-26)
**Executor:** Claude Opus 4.7 (Chris co-driving). Subscription-billed throughout — no openclaw agent dispatches.
**Per:** Hotfix 10 draft by Jade (v2, Inquisitor pre-audit `approved-with-modifications`: C1 static/js directory, C3 defer script ordering, C4 remove redundant DOMContentLoaded guards, C5 update DEPLOYMENT.md CSP verification). Plus T3.5 (history Total column truncation) added by Inquisitor as an in-scope side-find during pre-audit.
**Inquisitor post-audit:** PENDING — Chris to dispatch.
**Deploys:**
- `06e97e2` (2026-05-28) — T1+T2+T3+T3.5+T5 main commit
- `4eb452a` (2026-05-28) — T3.5 follow-on (overflow-x-auto on history + profiles)
- `bef334d` (2026-05-28) — Total/Panes column swap on history

---

## Completed: 2026-05-28

## Scope reality vs. plan

| Task | Status | Notes |
|---|---|---|
| T1 (externalize inline scripts) | ✅ done | 4 inline blocks → 3 external files (`static/js/quote-form.js`, `profile-loader.js`, `pdf-download.js`). `defer` ordering: quote-form → profile-loader → pdf-download (last conditional on `{% if result %}`). DOMContentLoaded guards stripped per C4. `grep -c '<script>' templates/index.html → 0`. |
| T2 (remove unsafe-inline) | ✅ done | `script-src` now `'self' js.stripe.com`. Live header verified. |
| T3 (regression) | ✅ done | pytest 84/18 (= H9a baseline, zero new failures). CSP header live-verified. Console clean. End-to-end quote → PDF → invoice on live PASS. |
| T3.5 (history Total clip) | ✅ done | First pass added `whitespace-nowrap` only; Chris's live screenshot showed Total still clipped at right edge — outer container's `overflow-hidden` was the actual culprit. Follow-on (`4eb452a`) swapped to `overflow-x-auto`. Also applied same fix to `templates/profiles.html` (same pattern, BASE RATE column clipped at 375px). |
| T4 (live QA) | ✅ done | Chris verified on `panefreequoting.com` after second Render deploy. Two small UX polish items surfaced and were folded in: profiles overflow fix, Panes/Total column swap on history (Chris preferred Total in initial viewport, Panes behind the scroll). |
| T5 (DEPLOYMENT.md) | ✅ done | §2.8 expanded with expected post-H10 CSP value + full CSP timeline (H2 → H8 → H9a → H10). §3 file-layout expanded with `static/css/`, `static/img/`, `static/js/` contents + the rule that any new client-side script must land in `static/js/` to preserve the minimum-viable `script-src`. §8.5 updated to reflect H10 completion. |

## Three-bullet summary

- **What was done:** Externalized all 4 inline `<script>` blocks in `index.html` (form-state persistence, profile data loader + populateRates, POST→GET URL rewrite, PDF download + invoice convert) into 3 CSP-safe external JS files under `static/js/`, then removed `'unsafe-inline'` from CSP `script-src`. CSP `script-src` is now `'self' js.stripe.com` — the minimum-viable allowlist for our deploy. Also fixed the history Total column truncation (T3.5) and folded in two UX polish items that surfaced during live QA (profiles overflow + history column swap). Documented the full CSP timeline in DEPLOYMENT.md so future operators understand how the allowlist evolved.
- **What was deferred:** `style-src 'unsafe-inline'` removal (still required for inline `<style>` font-family blocks in 15 templates — needs nonce/hash approach, separate sprint). render.yaml Blueprint conversion still on the backlog. Bug 1 AC3 (404/500 visual verification) still carried over from H8. A11y label warnings still on the backlog.
- **What surprised:** (1) **The workspace was restructured mid-sprint.** Window-quoting moved from `~/.openclaw/workspace/projects/window-quoting/` to `~/.openclaw/workspace/Lightmade-Software/window-quoting/` (Chris reorganized openclaw lanes by org). My tooling kept resolving the old path via what was apparently a temporary junction, until that junction broke mid-session and my Edit calls started failing with "File does not exist." Recovery: `find` to locate the new path, switch over, restart Flask from the right place (the zombie Flask from the OLD path produced a confusing `TemplateNotFound: login.html` while the new code was running locally — the templates dir was gone from the old location). The shared `projects.md` registry still points at the old path and should be updated for future `/sprint-status` invocations. (2) **T3.5 required two passes.** The first fix (`whitespace-nowrap` on the Total `<td>`) prevented the price from wrapping but didn't stop the outer container's `overflow-hidden` from clipping the column off-screen at mobile widths. Chris's live screenshot caught this immediately — needed `overflow-x-auto` on the container too. Worth remembering: cell-level wrap controls and container-level overflow are independent. (3) **Render's first deploy succeeded but served 502s briefly during the build.** Standard Render behavior, but I'd not seen it before — the poll loop just waits it out.
