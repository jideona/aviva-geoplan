#!/usr/bin/env node
// `expo export --platform web` copies public/ (manifest.json, sw.js, icons)
// into the output as-is, and does pick up app.json's web.themeColor as a
// <meta> tag — but it doesn't know this is meant to be an installable PWA,
// so it never links the manifest or adds the iOS home-screen tags. This
// patches index.html after export rather than hand-editing a generated
// file, so re-running `expo export` never silently drops the PWA wiring.
const fs = require('fs');
const path = require('path');

const outDir = process.argv[2] || 'dist-pwa';
const htmlPath = path.join(outDir, 'index.html');

if (!fs.existsSync(htmlPath)) {
  console.error(`patch-pwa-html: ${htmlPath} not found — run expo export first.`);
  process.exit(1);
}

let html = fs.readFileSync(htmlPath, 'utf8');

const tags = [
  '<link rel="manifest" href="/manifest.json">',
  '<link rel="icon" type="image/png" href="/favicon.png">',
  '<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">',
  '<meta name="apple-mobile-web-app-capable" content="yes">',
  '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">',
  '<meta name="apple-mobile-web-app-title" content="GeoPlan Survey">',
  '<meta name="mobile-web-app-capable" content="yes">',
].join('\n  ');

let changed = false;

if (html.includes('rel="manifest"')) {
  console.log('patch-pwa-html: manifest link already present, skipping.');
} else {
  html = html.replace('</head>', `  ${tags}\n</head>`);
  changed = true;
  console.log(`patch-pwa-html: PWA tags added to ${htmlPath}`);
}

// --- Design System Vol.4.1 §12: PWA app-shell config ---------------------

// §12.2 viewport: notch/home-indicator safe-area support via viewport-fit,
// but zoom must NOT be locked (accessibility — surveyors pinch-zoom photos
// and fine-detail map taps). Replaces whatever viewport tag Expo generated
// rather than appending a second, conflicting one.
const viewportRe = /<meta name="viewport"[^>]*>/;
const viewportTag = '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">';
if (viewportRe.test(html)) {
  if (!html.match(viewportRe)[0].includes('viewport-fit=cover')) {
    html = html.replace(viewportRe, viewportTag);
    changed = true;
    console.log('patch-pwa-html: viewport meta updated with viewport-fit=cover.');
  }
} else {
  html = html.replace('</head>', `  ${viewportTag}\n</head>`);
  changed = true;
  console.log('patch-pwa-html: viewport meta inserted.');
}

// §12.1 CSS reset + mandatory pressed-state block. Mirrors theme.ts's
// PRESSED_STYLE (scale 0.98 / opacity 0.85) so native Pressable and web
// :active feel identical. §12.4 desktop constraint: on wide/NOC viewports
// the app shell stays at a phone-like proportion instead of stretching full
// width — targets #app-root, which App.tsx sets via nativeID on web.
const shellCss = `<style id="gp-app-shell">
    *, *::before, *::after { box-sizing: border-box; }
    html, body, #root { margin: 0; padding: 0; height: 100%; }
    body {
      -webkit-tap-highlight-color: transparent;
      overscroll-behavior-y: contain;
    }
    [role="button"], button, a {
      -webkit-tap-highlight-color: transparent;
      transition: transform 100ms ease, opacity 100ms ease;
    }
    [role="button"]:active, button:active, a:active {
      transform: scale(0.98);
      opacity: 0.85;
    }
    #app-root {
      max-width: 600px;
      margin: 0 auto;
      min-height: 100vh;
      position: relative;
      box-shadow: 0 4px 12px rgba(13,27,75,0.12);
    }
  </style>`;
if (html.includes('id="gp-app-shell"')) {
  console.log('patch-pwa-html: app-shell CSS already present, skipping.');
} else {
  html = html.replace('</head>', `  ${shellCss}\n</head>`);
  changed = true;
  console.log('patch-pwa-html: app-shell CSS (reset + pressed-state + desktop constraint) added.');
}

// §12.3 context-menu handling: field use involves long-presses (swipe-row
// fallback menu, map pin placement) that must not trigger the OS/browser
// context menu — except inside real form fields, where long-press-to-select
// is expected. Exception list matches the CSS :active exception intent —
// INPUT/TEXTAREA/SELECT and any contentEditable node stay untouched.
const contextMenuScript = `<script id="gp-context-menu">
    document.addEventListener('contextmenu', function (e) {
      var t = e.target;
      var tag = t && t.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (t && t.isContentEditable)) return;
      e.preventDefault();
    }, { passive: false });
  </script>`;
if (html.includes('id="gp-context-menu"')) {
  console.log('patch-pwa-html: context-menu script already present, skipping.');
} else {
  html = html.replace('</head>', `  ${contextMenuScript}\n</head>`);
  changed = true;
  console.log('patch-pwa-html: context-menu-preventer script added.');
}

// Some Expo/Metro versions emit an ES module bundle (uses `import.meta`),
// which throws "Cannot use 'import.meta' outside a module" if the script
// tag loading it isn't itself type="module". Classic <script defer> bundles
// are unaffected by adding type="module" (defer is a no-op on modules, and
// modules are deferred by default), so this is safe to always apply.
const scriptTagRe = /<script src="([^"]+\.js)" defer><\/script>/;
if (scriptTagRe.test(html) && !html.includes('<script type="module"')) {
  html = html.replace(scriptTagRe, '<script type="module" src="$1"></script>');
  changed = true;
  console.log('patch-pwa-html: marked app bundle script as type="module".');
} else if (html.includes('<script type="module"')) {
  console.log('patch-pwa-html: app bundle script already type="module", skipping.');
}

if (changed) {
  fs.writeFileSync(htmlPath, html);
}
