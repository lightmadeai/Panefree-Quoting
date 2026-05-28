// Hotfix 10 — externalized from templates/index.html.
//
// Combines two previously-inline blocks:
//   1. Form state persistence (BUG-004, Sprint 4) — original line 194
//   2. POST→GET URL rewrite (history.replaceState) — original line 559
//
// Loaded with `defer` so it executes after the DOM is parsed; no
// DOMContentLoaded / readyState guards needed (Inquisitor C4).

// ---------------------------------------------------------------------------
// Block 1: form draft persistence
//
// BUG-004 (Sprint 4): persist quote-form state across navigation so a
// user who runs out of credits mid-fill can buy more and return without
// re-entering everything.
//
//   save:    on every input change (named fields + checked addons)
//   restore: on script load, only if no server-rendered values are
//            present (server values take precedence — they're from a
//            fresh /calculate post)
//   clear:   after a successful /generate response (the credit was
//            spent, the form data has been used)
//
// Storage is sessionStorage scoped to a single key so it's wiped when
// the browser/tab closes — no cross-session bleed.
(function () {
    const KEY = 'pf_quote_draft_v1';
    const form = document.getElementById('quote-form');
    if (!form) return;
    // Server-rendered "submitted_*" values mean the user just hit
    // /calculate and got the preview — don't clobber that with a stale
    // draft from sessionStorage.
    const labelEl = form.querySelector('[name="label"]');
    const serverHasValues = !!(labelEl && labelEl.value);

    function snapshot() {
        const data = { fields: {}, addons: [] };
        form.querySelectorAll('input[name], select[name], textarea[name]').forEach(el => {
            if (el.type === 'checkbox') {
                if (el.name === 'addon' && el.checked) data.addons.push(el.value);
            } else if (el.type === 'submit' || el.type === 'button') {
                /* skip */
            } else {
                data.fields[el.name] = el.value;
            }
        });
        return data;
    }
    function save() {
        try { sessionStorage.setItem(KEY, JSON.stringify(snapshot())); } catch (e) {}
    }
    function restore() {
        let raw;
        try { raw = sessionStorage.getItem(KEY); } catch (e) { return; }
        if (!raw) return;
        let data; try { data = JSON.parse(raw); } catch (e) { return; }
        if (!data || typeof data !== 'object') return;
        Object.entries(data.fields || {}).forEach(([name, v]) => {
            const el = form.querySelector(`[name="${CSS.escape(name)}"]`);
            if (el && (el.type !== 'checkbox') && el.value === '') el.value = v;
        });
        (data.addons || []).forEach(value => {
            const el = form.querySelector(`input[name="addon"][value="${CSS.escape(value)}"]`);
            if (el) el.checked = true;
        });
        // Re-fire change on the profile select so populateRates re-runs.
        const sel = form.querySelector('[name="profile_id"]');
        if (sel) sel.dispatchEvent(new Event('change'));
    }
    function clearDraft() {
        try { sessionStorage.removeItem(KEY); } catch (e) {}
    }

    // Expose the clearer so the /generate success handler can call it.
    window.__clearQuoteDraft = clearDraft;

    // Save on any input change. Debounced lightly — typing fires a lot
    // of events, no need to thrash sessionStorage on every keystroke.
    let t = null;
    form.addEventListener('input', () => { clearTimeout(t); t = setTimeout(save, 200); });
    form.addEventListener('change', save);

    if (!serverHasValues) {
        // defer guarantees the DOM is fully parsed before this runs,
        // so we can restore directly without waiting for DOMContentLoaded.
        restore();
    }
})();

// ---------------------------------------------------------------------------
// Block 3 (merged): POST→GET URL rewrite
//
// After a POST to /calculate the URL bar shows /calculate, so hitting
// Ctrl+R re-submits the form and the previous quote sticks around.
// Rewriting the URL to "/" makes refresh hit the fresh GET form
// instead. (Pure UX shim — server logic unchanged.)
//
// Pre-externalization this block was wrapped in {% if result %} so it
// only rendered after a POST. Now it runs on every page load, but the
// pathname guard makes it a no-op when there's nothing to rewrite.
(function () {
    if (window.location.pathname !== '/' && window.location.pathname !== '') {
        // Only rewrite if we landed on a non-root path that should
        // collapse back to /. The original /calculate POST destination
        // is the only known case; we keep the guard tight so an
        // accidental future route doesn't get silently rewritten.
        if (window.location.pathname === '/calculate') {
            window.history.replaceState({}, '', '/');
        }
    }
})();
