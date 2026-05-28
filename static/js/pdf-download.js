// Hotfix 10 — externalized from templates/index.html (block 4, line 620).
//
// PDF download + invoice conversion button logic. Originally only
// rendered when {% if result %}; index.html now uses the same
// conditional on the <script defer src="..."> tag so this file is only
// requested when a quote result is on screen.
//
// Depends on:
//   - DOM element 'quote-payload' (JSON data container, always rendered
//     alongside this script in the same {% if result %} block)
//   - window.__clearQuoteDraft (defined by quote-form.js, which loads
//     first in the defer queue)
(function () {
    const btn = document.getElementById('download-pdf-btn');
    const label = document.getElementById('download-pdf-label');
    const invBtn = document.getElementById('convert-invoice-btn');
    const invLabel = document.getElementById('convert-invoice-label');
    const errEl = document.getElementById('download-error');
    const badge = document.getElementById('credit-badge');
    const payload = JSON.parse(document.getElementById('quote-payload').textContent);

    let generatedQuoteId = null;

    btn.addEventListener('click', async function () {
        btn.disabled = true;
        errEl.classList.add('hidden');
        label.textContent = 'Generating…';

        try {
            const res = await fetch('/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
                },
                body: JSON.stringify(payload),
            });

            if (res.status === 402) {
                const body = await res.json().catch(() => ({}));
                window.location.href = body.redirect || '/top-up';
                return;
            }

            const data = await res.json();
            if (!res.ok || data.status !== 'success') {
                throw new Error(data.message || 'Failed to generate PDF.');
            }

            badge.textContent = data.credits_remaining + ' credits';
            label.textContent = 'Downloading…';
            // BUG-004: quote was generated successfully — wipe the
            // saved draft so the user gets a fresh form on return.
            if (typeof window.__clearQuoteDraft === 'function') window.__clearQuoteDraft();
            window.location.href = data.download_url;

            generatedQuoteId = data.quote_id;
            invBtn.disabled = false;
            invBtn.classList.remove('bg-slate-800', 'text-slate-300');
            invBtn.classList.add('bg-emerald-600', 'hover:bg-emerald-500', 'text-white');

            setTimeout(() => { label.textContent = 'Download Quote PDF'; btn.disabled = false; }, 1500);
        } catch (e) {
            errEl.textContent = e.message;
            errEl.classList.remove('hidden');
            label.textContent = 'Download Quote PDF';
            btn.disabled = false;
        }
    });

    invBtn.addEventListener('click', async function () {
        if (!generatedQuoteId) return;
        invBtn.disabled = true;
        errEl.classList.add('hidden');
        invLabel.textContent = 'Converting…';
        try {
            const res = await fetch(`/quotes/${generatedQuoteId}/pdf?type=INVOICE`, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
                },
            });
            const data = await res.json();
            if (!res.ok || data.status !== 'success') {
                throw new Error(data.message || 'Failed to convert to invoice.');
            }
            invLabel.textContent = 'Downloading…';
            window.location.href = data.download_url;
            setTimeout(() => { invLabel.textContent = 'Convert to Invoice (free)'; invBtn.disabled = false; }, 1500);
        } catch (e) {
            errEl.textContent = e.message;
            errEl.classList.remove('hidden');
            invLabel.textContent = 'Convert to Invoice (free)';
            invBtn.disabled = false;
        }
    });
})();
