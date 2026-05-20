# Hotfix 9a / T1 — Dynamic Class Audit

**Sprint:** Hotfix 9a (Tailwind CDN → compiled CSS)
**Task:** T1 — Dynamic class audit + safelist compilation
**Executor:** Claude Opus 4.7 (Chris-dispatched)
**Date:** 2026-05-19

---

## Scope

Identify Tailwind classes that the standard `content` scanner won't pick up — JS-manipulated, dynamically constructed, or otherwise hidden from a static class-attribute scan. These must go into the `safelist` of `tailwind.config.js` (T2) so the compiled CSS guarantees they exist.

**In scope (15 page templates):**
`404.html`, `500.html`, `account.html`, `account_delete.html`, `contact.html`, `forgot_password.html`, `history.html`, `index.html`, `login.html`, `profile_new.html`, `profiles.html`, `register.html`, `reset_password.html`, `settings.html`, `top_up.html`

**Out of scope:**
- `_nav.html`, `_footer.html` (partials — scanned via the templates that include them)
- `templates/email/` (no Tailwind usage — inline styles only)
- `static/js/` (does not exist yet; will be populated in Hotfix 9b / Hotfix 10)

---

## AC1 — Static class attribute scan

Standard Tailwind `content` scanning of `templates/**/*.html` will pick up every static `class="..."` attribute, including class strings that live inside Jinja conditional blocks (`{% if %}...{% endif %}`). No safelisting required for any class found this way.

Validated: `grep -rE 'class="[^"]+"' templates/ --include="*.html"` returns the expected set of utility classes across the 15 page templates. Scanner config in T2 will include `templates/**/*.html`.

---

## AC2 — JS-manipulated classes

`grep -rn "classList\." templates/ --include="*.html"` returned 11 hits, all in `templates/index.html`:

| Line | Operation | Class(es) |
|---|---|---|
| 361 | `panel.classList.remove`, `errEl.classList.add` | `hidden` |
| 362 | `panel.classList.add` | `hidden` |
| 369 | `errEl.classList.add` | `hidden` |
| 371 | `errEl.classList.remove` | `hidden` |
| 420 | `errEl.classList.remove` | `hidden` |
| 634 | `errEl.classList.add` | `hidden` |
| 667 | `invBtn.classList.remove` | `bg-slate-800`, `text-slate-300` |
| 668 | `invBtn.classList.add` | `bg-emerald-600`, `hover:bg-emerald-500`, `text-white` |
| 673 | `errEl.classList.remove` | `hidden` |
| 682 | `errEl.classList.add` | `hidden` |
| 701 | `errEl.classList.remove` | `hidden` |

**Unique classes (6):** `hidden`, `bg-slate-800`, `text-slate-300`, `bg-emerald-600`, `hover:bg-emerald-500`, `text-white`

These match the classes Inquisitor enumerated in the T1 AC2 reference exactly.

`grep -rn "className" templates/ --include="*.html"` returned zero hits. No `className = "..."` direct assignments.

`grep` for dynamically constructed class strings (string concat / template literals containing utility prefixes like `bg-`, `text-`, `border-`, `p-`, `m-`, `w-`, `h-`, `rounded`) returned only the static `class="..."` matches plus the L667-668 hits above. No string-built class names found.

---

## AC3 — Jinja-conditional classes

`grep -rn 'class="[^"]*{{' templates/ --include="*.html"` returned **zero hits** — no template uses a Jinja expression *inside* a `class="..."` attribute value (e.g. `class="text-{{ color }}-500"`).

The three `{% if %}` patterns that contain class attributes are all **static class strings inside conditional blocks**, which Tailwind's source scanner handles natively:

- `templates/top_up.html:64` — `<span class="text-blue-600">Most Popular</span>`
- `templates/top_up.html:79` — `<span class="text-emerald-600">{{ discount_pct }}% off Starter</span>`
- `templates/profile_new.html:129` — `class="w-4 h-4 text-blue-600 border-slate-300 rounded focus:ring-blue-500"` (the `{% if %}` controls a `checked` attribute, not the class)

No safelisting required for any of these.

---

## AC4 — Safelist array for `tailwind.config.js`

```js
// tailwind.config.js — safelist (T2)
safelist: [
  // JS-manipulated classes from templates/index.html (lines 361-701)
  // These are toggled via classList.add() / .remove() and would not be
  // visible to the standard `content` scanner.
  'hidden',
  'bg-slate-800',
  'text-slate-300',
  'bg-emerald-600',
  'hover:bg-emerald-500',
  'text-white',
],
```

**Total safelist entries: 6** (all from `index.html` runtime DOM manipulation).

---

## Notes for T2

- `content` paths should include `templates/**/*.html` to cover all 17 HTML files (15 page + 2 partials). Partials are included via Jinja `{% include %}` but the scanner reads them as their own source files anyway.
- `content` paths should ALSO include `static/js/**/*.js` per Inquisitor M3 — even though `static/js/` is empty today, Hotfix 9b (mobile nav drawer) and Hotfix 10 (CSP hardening) will populate it. Adding the path now means no config change later.
- Pin `tailwindcss@3.4.x` per Inquisitor M2 — CDN was serving Tailwind v3.x, class syntax in templates is v3-compatible. Tailwind v4 has breaking changes (renamed utilities, new engine).
- Email templates (`templates/email/*.html`) use inline `<style>` only — not Tailwind — and must NOT be added to `content`.

---

## Verification

```
$ grep -rn "classList\." templates/ --include="*.html" | wc -l
11

$ grep -rn "className" templates/ --include="*.html" | wc -l
0

$ grep -rn 'class="[^"]*{{' templates/ --include="*.html" | wc -l
0
```

T1 complete. Safelist enumerated, audit committed. Ready for T2.
