// Clean iOS app shell for GitHub Pages preview and future Capacitor build.
(function () {
  function byId(id) { return document.getElementById(id); }

  function removeWebsiteElements() {
    document.body.classList.add('eot-app-preview');

    const removeSelectors = [
      '#cookieBanner',
      '.cookie-banner',
      '.site-footer',
      'footer',
      '.source-note',
      '#shareWhatsapp',
      '#shareFacebook',
      '#shareX',
      '#shareLinkedin',
      '.share-panel a',
      'a[href*="privacy"]',
      'a[href*="guida"]',
      'a[href*="metodologia"]'
    ];

    removeSelectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((node) => node.remove());
    });

    ['btnShareTop', 'nativeShare'].forEach((id) => {
      const node = byId(id);
      if (node) {
        node.hidden = true;
        node.setAttribute('aria-hidden', 'true');
        node.style.display = 'none';
      }
    });

    const pdf = byId('downloadPdf');
    if (pdf) pdf.innerHTML = '<i class="fa-solid fa-file-pdf"></i> PDF';

    const copy = byId('copySummary');
    if (copy) copy.innerHTML = '<i class="fa-solid fa-copy"></i> Copia';
  }

  function simplifyHomeCopy() {
    const hero = document.querySelector('.screen[data-step="0"] .hero-card');
    if (!hero || hero.__iosHomeSimplified) return;
    hero.__iosHomeSimplified = true;

    const eyebrow = hero.querySelector('.eyebrow');
    const title = hero.querySelector('h1');
    const lead = hero.querySelector('.lead');

    if (eyebrow) eyebrow.textContent = 'App confronto auto';
    if (title) title.textContent = 'Elettrica o termica?';
    if (lead) {
      lead.textContent = 'Confronta due auto nel tuo uso reale: prezzo, energia, carburante, manutenzione, bollo e anni di possesso.';
    }
  }

  function run() {
    removeWebsiteElements();
    simplifyHomeCopy();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }

  window.addEventListener('load', run);
  setTimeout(run, 300);
  setTimeout(run, 1200);
})();
