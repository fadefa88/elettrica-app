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

function patchIndexForBundle() {
  const indexPath = path.join(out, 'index.html');
  if (!fs.existsSync(indexPath)) return;
  let html = fs.readFileSync(indexPath, 'utf8');
  html = html.replace(
    'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js',
    'vendor/jspdf.umd.min.js'
  );
  fs.writeFileSync(indexPath, html, 'utf8');
  console.log('Patched index.html to use bundled jsPDF');
}

fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });

files.forEach(copyFileSafe);
dirs.forEach(copyDirSafe);
vendorFiles.forEach((file) => copyExternalFileSafe(file.src, file.dest));
patchIndexForBundle();

const requiredFiles = ['index.html', 'app.js', 'styles.css'];
const missing = requiredFiles.filter((file) => !fs.existsSync(path.join(out, file)));
if (missing.length) {
  console.error(`Missing required iOS web files: ${missing.join(', ')}`);
  process.exit(1);
}

console.log('\n✅ Stable web bundle ready in www/');
