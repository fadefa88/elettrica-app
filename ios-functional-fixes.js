// iOS functional fixes loaded only in the generated app/preview bundle.
(function () {
  function byId(id) { return document.getElementById(id); }

  function activeStepIndex() {
    const active = document.querySelector('.screen.active');
    return active ? Number(active.dataset.step || 0) : 0;
  }

  function isReportActive() {
    return activeStepIndex() === 7 || !!document.querySelector('.screen[data-step="7"].active');
  }

  function clickNextSafely() {
    const next = byId('nextStep');
    if (!next || next.disabled) return false;
    next.click();
    return true;
  }

  function forceReportAfterChoiceGuide() {
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      if (isReportActive()) {
        clearInterval(timer);
        return;
      }
      const current = activeStepIndex();
      if (current >= 7) {
        clearInterval(timer);
        return;
      }
      clickNextSafely();
      if (tries >= 10) clearInterval(timer);
    }, 90);
  }

  function watchChoiceGuideFinish() {
    document.addEventListener('click', (event) => {
      const target = event.target instanceof Element ? event.target.closest('#cgNext') : null;
      if (!target) return;
      const text = (target.textContent || '').toLowerCase();
      if (text.includes('report') || text.includes('queste auto')) {
        setTimeout(forceReportAfterChoiceGuide, 160);
        setTimeout(forceReportAfterChoiceGuide, 500);
      }
    }, true);
  }

  function repairTrimSelectors() {
    ['ev', 'ice'].forEach((kind) => {
      const trim = byId(kind === 'ev' ? 'evTrimSelect' : 'iceTrimSelect');
      const hidden = byId(kind === 'ev' ? 'evSelect' : 'iceSelect');
      if (!trim || !hidden || trim.__iosFunctionalFixBound) return;

      const sync = () => {
        if (!trim.value) return;
        if (!Array.from(hidden.options).some((option) => option.value === trim.value)) {
          hidden.insertAdjacentHTML('afterbegin', '<option value="' + trim.value.replace(/"/g, '&quot;') + '">' + trim.value + '</option>');
        }
        hidden.value = trim.value;
        try { hidden.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
        try { hidden.dispatchEvent(new Event('change', { bubbles: true })); } catch (_) {}
        try { if (typeof setAutoFields === 'function') setAutoFields(); } catch (_) {}
        try { if (typeof calculate === 'function') calculate(); } catch (_) {}
        try { if (typeof updateNavigation === 'function') updateNavigation(); } catch (_) {}
      };

      trim.addEventListener('change', sync);
      trim.addEventListener('input', sync);
      trim.__iosFunctionalFixBound = true;
    });
  }

  function keepHiddenBoundControls() {
    ['nativeShare', 'btnShareTop'].forEach((id) => {
      let node = byId(id);
      if (!node) {
        node = document.createElement('button');
        node.id = id;
        node.type = 'button';
        node.textContent = id;
        document.body.appendChild(node);
      }
      node.hidden = true;
      node.setAttribute('aria-hidden', 'true');
      node.style.display = 'none';
    });
  }

  function installSafeBindGuards() {
    // app.js sometimes binds after async catalog loading. These guards prevent old app-only layers
    // or preview cache from breaking the bind when share controls are hidden/removed.
    keepHiddenBoundControls();
    window.addEventListener('error', (event) => {
      const msg = String(event.message || '');
      if (msg.includes('nativeShare') || msg.includes('btnShareTop')) {
        keepHiddenBoundControls();
      }
    }, true);
  }

  function photovoltaicConfigured() {
    const noPv = !!byId('noPv')?.checked;
    const unknownPv = !!byId('unknownPv')?.checked;
    const solar = Number(byId('solarShare')?.value || 0);
    return noPv || unknownPv || solar > 0;
  }

  function showPvHint(show) {
    const screen = document.querySelector('.screen[data-step="5"]');
    if (!screen) return;
    let hint = byId('iosPvRequiredHint');
    if (!hint) {
      hint = document.createElement('div');
      hint.id = 'iosPvRequiredHint';
      hint.className = 'ios-validation-hint';
      hint.textContent = 'Scegli una delle opzioni: ho fotovoltaico, non ho fotovoltaico oppure non lo so. Se hai fotovoltaico, inserisci una percentuale maggiore di 0.';
      screen.appendChild(hint);
    }
    hint.hidden = !show;
  }

  function patchProceedValidation() {
    if (window.__iosCanProceedPatched) return;
    let original;
    try { original = canProceed; } catch (_) { return; }
    if (typeof original !== 'function') return;

    try {
      canProceed = function () {
        if (activeStepIndex() === 5) {
          const ok = photovoltaicConfigured();
          showPvHint(!ok);
          return ok;
        }
        return original.apply(this, arguments);
      };
      window.__iosCanProceedPatched = true;
    } catch (_) {}
  }

  function patchPvInputs() {
    ['noPv', 'unknownPv', 'solarShare'].forEach((id) => {
      const el = byId(id);
      if (!el || el.__iosPvBound) return;
      el.addEventListener('input', () => {
        showPvHint(activeStepIndex() === 5 && !photovoltaicConfigured());
        try { if (typeof updateNavigation === 'function') updateNavigation(); } catch (_) {}
      });
      el.addEventListener('change', () => {
        showPvHint(activeStepIndex() === 5 && !photovoltaicConfigured());
        try { if (typeof updateNavigation === 'function') updateNavigation(); } catch (_) {}
      });
      el.__iosPvBound = true;
    });
  }

  function run() {
    keepHiddenBoundControls();
    repairTrimSelectors();
    patchProceedValidation();
    patchPvInputs();
    if (activeStepIndex() === 5) showPvHint(!photovoltaicConfigured());
  }

  installSafeBindGuards();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      watchChoiceGuideFinish();
      run();
    });
  } else {
    watchChoiceGuideFinish();
    run();
  }

  setInterval(run, 700);
})();
