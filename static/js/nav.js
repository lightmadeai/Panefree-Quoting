// Hotfix 9b — Mobile nav drawer toggle.
//
// Loaded by templates/_nav.html via:
//   <script defer src="{{ url_for('static', filename='js/nav.js') }}">
//
// 'defer' guarantees the script executes after the DOM is parsed,
// so the elements we query are guaranteed to exist. No need for a
// DOMContentLoaded listener.
//
// This file is external (not inline) so it remains valid after
// Hotfix 10 removes 'unsafe-inline' from CSP script-src.
(function () {
  'use strict';

  const hamburger = document.getElementById('nav-hamburger');
  const closeBtn = document.getElementById('nav-hamburger-close');
  const drawer = document.getElementById('mobile-drawer');
  const overlay = document.getElementById('mobile-drawer-overlay');

  // _nav.html is included on every authenticated page. If the partial
  // somehow renders without all four elements (e.g. a refactor breaks
  // an ID), silently bail rather than throwing.
  if (!hamburger || !drawer || !overlay) return;

  function isOpen() {
    return !drawer.classList.contains('translate-x-full');
  }

  function open() {
    drawer.classList.remove('translate-x-full');
    drawer.classList.add('translate-x-0');
    overlay.classList.remove('hidden');
    hamburger.setAttribute('aria-expanded', 'true');
    drawer.setAttribute('aria-hidden', 'false');
    // Prevent body scroll while the drawer is open so the user
    // isn't simultaneously scrolling the page underneath.
    document.body.style.overflow = 'hidden';
  }

  function close() {
    drawer.classList.add('translate-x-full');
    drawer.classList.remove('translate-x-0');
    overlay.classList.add('hidden');
    hamburger.setAttribute('aria-expanded', 'false');
    drawer.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  hamburger.addEventListener('click', open);
  if (closeBtn) closeBtn.addEventListener('click', close);
  overlay.addEventListener('click', close);

  // Escape key closes the drawer (standard a11y pattern for off-canvas menus).
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && isOpen()) close();
  });

  // Tapping any nav link in the drawer closes it before navigating —
  // makes back-button behavior feel right and avoids a stale-open
  // drawer flashing into view on the next page render.
  drawer.querySelectorAll('a').forEach(function (a) {
    a.addEventListener('click', close);
  });

  // Defensive: if the viewport is resized up past the md breakpoint
  // (768px) while the drawer is open (e.g. landscape rotation, devtools
  // toggle), close it so the desktop nav doesn't render behind an
  // open drawer.
  window.addEventListener('resize', function () {
    if (window.innerWidth >= 768 && isOpen()) close();
  });
})();
