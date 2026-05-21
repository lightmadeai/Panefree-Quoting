/** @type {import('tailwindcss').Config} */
module.exports = {
  // Scan all Jinja templates (page templates + partials). Email templates
  // under templates/email/ are intentionally excluded — they use inline
  // <style> only and don't reference Tailwind utilities.
  //
  // static/js/**/*.js is included for future-proofing: Hotfix 9b adds
  // static/js/nav.js for the mobile drawer, and Hotfix 10 externalizes
  // index.html's inline scripts into static/js/. Including the path now
  // means those sprints don't have to touch this config.
  content: [
    './templates/**/*.html',
    '!./templates/email/**',
    './static/js/**/*.js',
  ],
  safelist: [
    // JS-manipulated classes from templates/index.html (lines 361-701)
    // toggled via classList.add() / .remove(). Not visible to the standard
    // content scanner. See PLANNING/research/class-audit.md for the full
    // line-by-line audit.
    'hidden',
    'bg-slate-800',
    'text-slate-300',
    'bg-emerald-600',
    'hover:bg-emerald-500',
    'text-white',
    // Hotfix 9b: mobile nav drawer transform classes — toggled via
    // classList.add/remove in static/js/nav.js to slide the drawer.
    // Both states appear statically in _nav.html too (initial closed
    // state), but kept in the safelist for defense against future
    // refactors that might remove the static reference.
    'translate-x-full',
    'translate-x-0',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
