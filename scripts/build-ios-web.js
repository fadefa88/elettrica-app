const fs = require('fs');
const path = require('path');

const root = process.cwd();
const out = path.join(root, 'www');

// App preview bundle: keep only the app shell, not the public website pages.
const files = [
  'index.html',
  'app.js',
  'choice-guide.js',
  'motornet-base-trim-ui.js',
  'motornet-ui.js',
  'tax-superbollo-fix.js',
  'pwa-fixes.js',
  'car-images.css',
  'styles.css',
  'app-ios-shell.css',
  'app-ios-shell.js',
  'manifest.webmanifest'
];

const dirs = [
  'assets',
  'data'
];

const vendorFiles = [
  {
    src: 'node_modules/jspdf/dist/jspdf.umd.min.js',
    dest: 'vendor/jspdf.umd.min.js'
  }
];

const ignoredPathParts = [
  '/.git/',
  '/.github/',
  '/ios/',
  '/node_modules/',
  '/www/',
  '/scripts/',
  '/reports/'
];

const ignoredExtensions = [
  '.psd',
  '.ai',
  '.zip',
  '.log'
];

function sourcePath(relPath) {
  return path.join(root, relPath);
}

function exists(relPath) {
  return fs.existsSync(sourcePath(relPath));
}

function shouldCopy(source) {
  const normalized = source.replace(/\\/g, '/');
  if (ignoredPathParts.some((part) => normalized.includes(part))) return false;
  if (ignoredExtensions.some((ext) => normalized.toLowerCase().endsWith(ext))) return false;
  return true;
}

function copyFileSafe(relPath) {
  if (!exists(relPath)) return;
  const src = sourcePath(relPath);
  const dest = path.join(out, relPath);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
  console.log(`Copied file: ${relPath}`);
}

function copyExternalFileSafe(srcRelPath, destRelPath) {
  const src = sourcePath(srcRelPath);
  if (!fs.existsSync(src)) {
    console.warn(`Optional vendor file missing: ${srcRelPath}`);
    return;
  }
  const dest = path.join(out, destRelPath);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
  console.log(`Copied vendor: ${destRelPath}`);
}

function copyDirSafe(relPath) {
  if (!exists(relPath)) return;
  const src = sourcePath(relPath);
  const dest = path.join(out, relPath);
  fs.cpSync(src, dest, {
    recursive: true,
    force: true,
    filter: shouldCopy
  });
  console.log(`Copied dir: ${relPath}`);
}

function injectBefore(html, needle, snippet) {
  if (html.includes(snippet.trim())) return html;
  return html.replace(needle, `${snippet}\n${needle}`);
}

function patchAppJsForBundle() {
  const appPath = path.join(out, 'app.js');
  if (!fs.existsSync(appPath)) return;
  let js = fs.readFileSync(appPath, 'utf8');

  // The app preview hides website share buttons. Make app.js tolerant if those nodes are hidden/removed.
  const unsafeShareBind = "$('downloadPdf').onclick=downloadPdf;$('nativeShare').onclick=shareNative;$('btnShareTop').onclick=shareNative;$('copySummary').onclick=copySummary;";
  const safeShareBind = "if($('downloadPdf'))$('downloadPdf').onclick=downloadPdf;if($('nativeShare'))$('nativeShare').onclick=shareNative;if($('btnShareTop'))$('btnShareTop').onclick=shareNative;if($('copySummary'))$('copySummary').onclick=copySummary;";
  if (js.includes(unsafeShareBind)) {
    js = js.replace(unsafeShareBind, safeShareBind);
  }

  fs.writeFileSync(appPath, js, 'utf8');
  console.log('Patched app.js bindings for app preview');
}

function patchIndexForBundle() {
  const indexPath = path.join(out, 'index.html');
  if (!fs.existsSync(indexPath)) return;
  let html = fs.readFileSync(indexPath, 'utf8');

  html = html.replace(
    'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js',
    'vendor/jspdf.umd.min.js'
  );

  // Remove public-website cookie helper from the app preview.
  html = html.replace(/\s*<link rel="stylesheet" href="cookie-banner\.css">/g, '');
  html = html.replace(/\s*<script src="cookie-banner\.js[^>]*><\/script>/g, '');

  // Remove full-site informational page links from the app preview home.
  html = html.replace(/<p class="source-note">[\s\S]*?<\/p>/g, '');

  html = html.replace('<body>', '<body class="eot-app-preview">');

  html = injectBefore(
    html,
    '</head>',
    '  <link rel="stylesheet" href="app-ios-shell.css?v=app-ios-shell-1">'
  );

  html = injectBefore(
    html,
    '</body>',
    '<script src="app-ios-shell.js?v=app-ios-shell-1"></script>'
  );

  fs.writeFileSync(indexPath, html, 'utf8');
  console.log('Patched index.html as clean app preview');
}

fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });

files.forEach(copyFileSafe);
dirs.forEach(copyDirSafe);
vendorFiles.forEach((file) => copyExternalFileSafe(file.src, file.dest));
patchAppJsForBundle();
patchIndexForBundle();

// SPA fallback for GitHub Pages: everything returns the app, not website pages.
fs.copyFileSync(path.join(out, 'index.html'), path.join(out, '404.html'));

const requiredFiles = ['index.html', '404.html', 'app.js', 'styles.css', 'app-ios-shell.css', 'app-ios-shell.js'];
const missing = requiredFiles.filter((file) => !fs.existsSync(path.join(out, file)));
if (missing.length) {
  console.error(`Missing required app preview files: ${missing.join(', ')}`);
  process.exit(1);
}

console.log('\n✅ iOS-style app preview bundle ready in www/');
