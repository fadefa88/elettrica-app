const fs = require('fs');
const path = require('path');

const root = process.cwd();
const out = path.join(root, 'www');

const files = [
  'index.html',
  'guida.html',
  'metodologia.html',
  'privacy.html',
  '404.html',
  'app.js',
  'choice-guide.js',
  'motornet-base-trim-ui.js',
  'motornet-ui.js',
  'tax-superbollo-fix.js',
  'pwa-fixes.js',
  'car-images.css',
  'styles.css',
  'cookie-banner.css',
  'cookie-banner.js',
  'ios-app.css',
  'ios-app.js',
  'robots.txt',
  'sitemap.xml',
  'manifest.webmanifest',
  '_headers',
  '_redirects'
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

function injectIosAppLayer() {
  const indexPath = path.join(out, 'index.html');
  if (!fs.existsSync(indexPath)) return;

  let html = fs.readFileSync(indexPath, 'utf8');

  // Use bundled assets in the native app. Remote CDN dependencies are fragile in WebView/offline mode.
  html = html.replace(
    'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js',
    'vendor/jspdf.umd.min.js'
  );

  if (!html.includes('ios-app.css')) {
    html = html.replace(
      '</head>',
      '  <link rel="stylesheet" href="ios-app.css?v=ios-app-2">\n</head>'
    );
  }

  if (!html.includes('ios-app.js')) {
    html = html.replace(
      '</body>',
      '<script src="ios-app.js?v=ios-app-2"></script>\n</body>'
    );
  }

  html = html.replace('<html lang="it">', '<html lang="it" class="eot-ios-app">');
  html = html.replace('<body>', '<body class="eot-ios-app">');

  // In the native app the cookie banner, web footer and web social links are not useful.
  // CSS hides them before the JavaScript app layer runs, avoiding a visible flash.
  fs.writeFileSync(indexPath, html, 'utf8');
  console.log('Injected iOS app stylesheet, script and body class');
}

fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });

files.forEach(copyFileSafe);
dirs.forEach(copyDirSafe);
vendorFiles.forEach((file) => copyExternalFileSafe(file.src, file.dest));
injectIosAppLayer();

const requiredFiles = ['index.html', 'app.js', 'styles.css', 'ios-app.css', 'ios-app.js'];
const missing = requiredFiles.filter((file) => !fs.existsSync(path.join(out, file)));
if (missing.length) {
  console.error(`Missing required iOS web files: ${missing.join(', ')}`);
  process.exit(1);
}

console.log('\n✅ iOS web bundle ready in www/');
