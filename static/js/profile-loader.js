// Hotfix 10 — externalized from templates/index.html.
//
// Two IIFEs, both originally in the line-275 inline <script> block:
//   1. populateRates() — fills floor/addon rate fields from the selected
//      pricing profile (placeholders for floor/addon overrides per
//      BUG-006; actual values for tax + callout).
//   2. New-profile form handler — the inline "+ New Profile" panel
//      below the dropdown.
//
// Loaded with `defer` so the DOM is fully parsed at execution time;
// the original DOMContentLoaded / readyState guards are dropped per
// Inquisitor C4. Execution order is also after quote-form.js (per
// the <script defer> sequence in index.html), so window.__clearQuoteDraft
// is defined by the time pdf-download.js needs it downstream.

// ---------------------------------------------------------------------------
// IIFE 1: populate rate fields from profile data
(function () {
    const profilesData = JSON.parse(document.getElementById('profiles-data').textContent);
    const select = document.getElementById('profile-select');

    const setVal = (name, v) => {
        const el = document.querySelector(`[name="${name}"]`);
        if (el && v !== undefined && v !== null) el.value = v;
    };
    // BUG-006 fix (Sprint 4): floor + addon override fields use
    // placeholder rather than value so the engine doesn't see them as
    // "custom" when the user accepts the default. Pre-fix, populateRates
    // wrote the computed default into .value, which engine.py then
    // flagged as an override on every line item — so every quote PDF
    // read "(Custom Rate)" even when nothing was customized. Setting
    // placeholder leaves .value empty unless the user explicitly types
    // a different number.
    const setPlaceholder = (name, v) => {
        const el = document.querySelector(`[name="${name}"]`);
        if (el && v !== undefined && v !== null) {
            el.placeholder = v;
            // Also clear any stale value left over from a previous
            // profile selection — switching profiles must not leave
            // the old default's number in the field.
            el.value = '';
        }
    };

    function populateRates(profileName) {
        const p = profilesData[profileName];
        if (!p) return;
        const br = Number(p.base_pane_rate) || 0;
        const ss = p.story_surcharges || {};
        setPlaceholder('override_floor1', (br * (Number(ss.floor1) || 1)).toFixed(2));
        setPlaceholder('override_floor2', (br * (Number(ss.floor2) || 1)).toFixed(2));
        setPlaceholder('override_floor3', (br * (Number(ss.floor3) || 1)).toFixed(2));

        const ar = p.add_on_rates || {};
        const addonMap = {
            'Screen Cleaning': 'override_addon_Screen_Cleaning',
            'Track Cleaning': 'override_addon_Track_Cleaning',
            'Hard Water Treatment': 'override_addon_Hard_Water_Treatment',
        };
        for (const [addonName, field] of Object.entries(addonMap)) {
            const v = ar[addonName];
            setPlaceholder(field, v !== undefined ? Number(v).toFixed(2) : '');
        }

        // Callout and tax remain as actual values (auto-filled +
        // editable). These don't drive a "(Custom Rate)" label —
        // tax_override is a separate engine code path, callout is a
        // registry mutation. So pre-filling them is intended UX.
        setVal('tax_override_percent', (Number(p.tax_rate || 0) * 100).toFixed(1));
        setVal('callout_override', Number(p.base_callout_fee || 0).toFixed(2));
    }

    select.addEventListener('change', () => populateRates(select.value));
    // defer means the form is fully parsed by the time we run, so we
    // can call populateRates immediately without DOMContentLoaded.
    if (select.value) populateRates(select.value);

    // Expose for the new-profile IIFE below + future callers.
    window.__populateRates = populateRates;
    window.__profilesData = profilesData;
})();

// ---------------------------------------------------------------------------
// IIFE 2: inline "+ New Profile" creation panel
(function () {
    const toggle = document.getElementById('new-profile-toggle');
    const closeBtn = document.getElementById('new-profile-close');
    const cancelBtn = document.getElementById('new-profile-cancel');
    const panel = document.getElementById('new-profile-panel');
    const saveBtn = document.getElementById('new-profile-save');
    const errEl = document.getElementById('new-profile-error');
    const select = document.getElementById('profile-select');

    const open = () => { panel.classList.remove('hidden'); errEl.classList.add('hidden'); };
    const close = () => { panel.classList.add('hidden'); };

    toggle.addEventListener('click', open);
    closeBtn.addEventListener('click', close);
    cancelBtn.addEventListener('click', close);

    saveBtn.addEventListener('click', async function () {
        errEl.classList.add('hidden');
        const name = document.getElementById('np-name').value.trim();
        if (!name) { errEl.textContent = 'Name is required.'; errEl.classList.remove('hidden'); return; }

        const num = id => parseFloat(document.getElementById(id).value);
        const price_data = {
            base_pane_rate: num('np-base-rate'),
            base_callout_fee: num('np-callout'),
            tax_rate: num('np-tax') / 100,  // user enters percent, stored as decimal
            story_surcharges: { floor1: num('np-f1'), floor2: num('np-f2'), floor3: num('np-f3') },
            add_on_rates: {
                'Screen Cleaning': num('np-screen'),
                'Track Cleaning': num('np-track'),
                'Hard Water Treatment': num('np-hardwater'),
            },
        };

        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving…';
        try {
            const res = await fetch('/api/profiles/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
                },
                body: JSON.stringify({
                    name,
                    price_data,
                    make_default: document.getElementById('np-default').checked,
                }),
            });
            const body = await res.json();
            if (!res.ok || body.status !== 'success') throw new Error(body.message || 'Save failed');

            // Add + select new profile in the dropdown
            const opt = document.createElement('option');
            opt.value = body.profile.name;
            opt.textContent = body.profile.name;
            opt.selected = true;
            select.appendChild(opt);
            select.value = body.profile.name;

            // Register the new profile's price_data for client-side
            // auto-fill, then populate the rate fields with it.
            if (window.__profilesData) window.__profilesData[body.profile.name] = price_data;
            if (window.__populateRates) window.__populateRates(body.profile.name);

            close();
        } catch (e) {
            errEl.textContent = e.message;
            errEl.classList.remove('hidden');
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save & Use';
        }
    });
})();
