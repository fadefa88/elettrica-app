// iOS Capacitor app layer: app-only UX enhancements.
// This file is copied/injected only by scripts/build-ios-web.js.
(function () {
  const isNativeScheme = location.protocol === 'capacitor:' || location.hostname === 'localhost';
  document.documentElement.classList.add('eot-ios-app');

  function removeWebOnlyElements() {
    const selectors = [
      '#cookieBanner',
      '.cookie-banner',
      '.site-footer',
      '.app-footer',
      'footer',
      '.top-actions',
      '#btnShareTop',
      '#nativeShare',
      '#shareWhatsapp',
      '#shareFacebook',
      '#shareX',
      '#shareLinkedin',
      '.share-panel a',
      'a[href="/guida.html"]'
    ];

    selectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((node) => node.remove());
    });
  }

  function nativeCopyFallback(text) {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(() => {});
    }
  }

  function tuneHero() {
    const hero = document.querySelector('[data-step="0"] .hero-card');
    if (!hero) return;

    const eyebrow = hero.querySelector('.eyebrow');
    const title = hero.querySelector('h1');
    const lead = hero.querySelector('.lead');

    if (eyebrow) eyebrow.textContent = 'Calcolatore auto';
    if (title) title.textContent = 'Elettrica o termica?';
    if (lead) {
      lead.textContent = 'Scegli due auto, inserisci km e ricarica: l’app calcola costo totale, risparmio e break-even.';
    }

    const cards = hero.querySelectorAll('.info-grid > div');
    const copy = [
      ['1', 'Elettrica', 'Scegli modello o inserisci i dati.'],
      ['2', 'Termica', 'Confronta la vera alternativa.'],
      ['3', 'Risultato', 'PDF e riepilogo finale.']
    ];

    cards.forEach((card, index) => {
      const item = copy[index];
      if (!item) return;
      const icon = card.querySelector('i');
      const titleNode = card.querySelector('b');
      const textNode = card.querySelector('span');
      if (icon) icon.outerHTML = '<span class="ios-step-dot">' + item[0] + '</span>';
      if (titleNode) titleNode.textContent = item[1];
      if (textNode) textNode.textContent = item[2];
    });
  }

  function tuneLabels() {
    const stepTitle = document.getElementById('stepTitleSmall');
    if (stepTitle && stepTitle.textContent.trim() === 'Benvenuto') {
      stepTitle.textContent = 'Setup rapido';
    }

    const pdfButton = document.getElementById('downloadPdf');
    if (pdfButton) pdfButton.innerHTML = '<i class="fa-solid fa-file-pdf"></i> Esporta report';

    const copyButton = document.getElementById('copySummary');
    if (copyButton) copyButton.innerHTML = '<i class="fa-solid fa-copy"></i> Copia dati';
  }

  function tuneInputs() {
    const inputs = document.querySelectorAll('input, select, textarea');
    inputs.forEach((input) => {
      input.setAttribute('autocomplete', 'off');
      input.setAttribute('autocorrect', 'off');
      input.setAttribute('autocapitalize', 'none');
      input.setAttribute('spellcheck', 'false');

      input.addEventListener('focus', () => {
        setTimeout(() => {
          input.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' });
        }, 120);
      });
    });
  }

  function tuneSharePanel() {
    const panel = document.querySelector('.share-panel');
    if (!panel) return;

    const pdfButton = document.getElementById('downloadPdf');
    const copyButton = document.getElementById('copySummary');
    panel.innerHTML = '';
    if (pdfButton) panel.appendChild(pdfButton);
    if (copyButton) panel.appendChild(copyButton);

    if (copyButton) {
      copyButton.addEventListener('click', () => {
        const text = document.getElementById('explainBox')?.innerText || document.getElementById('reportArea')?.innerText || '';
        nativeCopyFallback(text);
      });
    }
  }

  function markCompactSections() {
    document.querySelectorAll('.source-note').forEach((node) => node.remove());
    document.querySelectorAll('.muted').forEach((node) => {
      if ((node.textContent || '').length > 130) node.classList.add('ios-muted-compact');
    });
  }

  function init() {
    document.body.classList.add('eot-ios-app');
    removeWebOnlyElements();
    tuneHero();
    tuneLabels();
    tuneInputs();
    tuneSharePanel();
    markCompactSections();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Re-run after the main app mutates screens/results.
  setTimeout(init, 400);
  setTimeout(init, 1200);
})();
