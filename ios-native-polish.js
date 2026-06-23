// Native iOS polish layer: loaded only in the Capacitor/TestFlight bundle.
(function () {
  const run = () => {
    document.documentElement.classList.add('eot-ios-app');
    document.body.classList.add('eot-ios-app');

    removeWebArtifacts();
    tuneLandingCopy();
    tuneStepLabels();
    tuneResultActions();
    tuneKeyboardBehavior();
    addNativeHints();
  };

  function removeWebArtifacts() {
    const selectors = [
      '#cookieBanner', '.cookie-banner', '.cookie-consent',
      'footer', '.site-footer', '.app-footer',
      '.top-actions', '#btnShareTop', '#nativeShare',
      '#shareWhatsapp', '#shareFacebook', '#shareX', '#shareLinkedin',
      '.social-share', '.social-row', '.web-share',
      'a[href*="facebook.com"]', 'a[href*="twitter.com"]', 'a[href*="x.com"]',
      'a[href*="linkedin.com"]', 'a[href*="whatsapp"]'
    ];

    selectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((node) => node.remove());
    });
  }

  function tuneLandingCopy() {
    const hero = document.querySelector('[data-step="0"] .hero-card');
    if (!hero) return;

    const eyebrow = hero.querySelector('.eyebrow');
    const title = hero.querySelector('h1');
    const lead = hero.querySelector('.lead');

    if (eyebrow) eyebrow.textContent = 'Decisione rapida';
    if (title) title.textContent = 'Elettrica o termica?';
    if (lead) {
      lead.textContent = 'Calcola quale auto costa meno nel tuo uso reale: acquisto, energia, carburante, bollo e manutenzione.';
    }

    const cards = hero.querySelectorAll('.info-grid > div');
    const copy = [
      ['1', 'Scegli elettrica', 'Modello reale oppure dati manuali.'],
      ['2', 'Scegli termica', 'Benzina, diesel o ibrida da confrontare.'],
      ['3', 'Leggi il verdetto', 'Risparmio, pareggio e report PDF.']
    ];

    cards.forEach((card, index) => {
      const item = copy[index];
      if (!item) return;
      const icon = card.querySelector('i, .ios-step-dot');
      const titleNode = card.querySelector('b, strong');
      const textNode = card.querySelector('span:last-child, p');
      if (icon && !icon.classList.contains('ios-step-dot')) icon.outerHTML = '<span class="ios-step-dot">' + item[0] + '</span>';
      if (icon && icon.classList.contains('ios-step-dot')) icon.textContent = item[0];
      if (titleNode) titleNode.textContent = item[1];
      if (textNode) textNode.textContent = item[2];
    });
  }

  function tuneStepLabels() {
    const map = {
      'Benvenuto': 'Setup',
      'Auto elettrica': 'Elettrica',
      'Auto termica': 'Termica',
      'Risultati': 'Verdetto'
    };

    document.querySelectorAll('.steps-label span, #stepTitleSmall').forEach((node) => {
      const text = (node.textContent || '').trim();
      if (map[text]) node.textContent = map[text];
    });

    document.querySelectorAll('h2').forEach((node) => {
      const text = (node.textContent || '').trim().toLowerCase();
      if (text.includes('risult')) node.textContent = 'Il verdetto';
    });
  }

  function tuneResultActions() {
    const panel = document.querySelector('.share-panel');
    const pdf = document.getElementById('downloadPdf');
    const copy = document.getElementById('copySummary');
    if (!panel || (!pdf && !copy)) return;

    panel.querySelectorAll('a').forEach((node) => node.remove());

    if (pdf) {
      pdf.innerHTML = '<i class="fa-solid fa-file-pdf"></i> Esporta report';
      pdf.setAttribute('type', 'button');
      if (!panel.contains(pdf)) panel.appendChild(pdf);
    }

    if (copy) {
      copy.innerHTML = '<i class="fa-solid fa-copy"></i> Copia riepilogo';
      copy.setAttribute('type', 'button');
      if (!panel.contains(copy)) panel.appendChild(copy);
    }
  }

  function tuneKeyboardBehavior() {
    document.querySelectorAll('input, select, textarea').forEach((el) => {
      el.setAttribute('autocomplete', 'off');
      el.setAttribute('autocorrect', 'off');
      el.setAttribute('autocapitalize', 'none');
      el.setAttribute('spellcheck', 'false');

      el.addEventListener('focus', () => {
        setTimeout(() => {
          try {
            el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' });
          } catch (_) {
            el.scrollIntoView(false);
          }
        }, 160);
      }, { passive: true });
    });
  }

  function addNativeHints() {
    const result = document.querySelector('.result-card');
    if (result && !result.querySelector('.app-note')) {
      const note = document.createElement('p');
      note.className = 'app-note';
      note.textContent = 'Suggerimento: esporta il report per confrontare l’acquisto con calma o condividerlo dal menu iPhone.';
      result.appendChild(note);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }

  setTimeout(run, 300);
  setTimeout(run, 900);
  setTimeout(run, 1800);
})();
