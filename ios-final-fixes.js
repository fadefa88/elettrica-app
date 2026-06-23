// Final iOS app fixes. Loaded last in the generated www bundle.
(function () {
  function byId(id) { return document.getElementById(id); }
  function clean(v) { return String(v || '').replace(/\s+/g, ' ').trim(); }
  function lower(v) { return clean(v).toLowerCase(); }

  function cars(kind) {
    try {
      return kind === 'ev' ? (Array.isArray(EV) ? EV : []) : (Array.isArray(IC) ? IC : []);
    } catch (_) {
      return [];
    }
  }

  function activeStep() {
    const active = document.querySelector('.screen.active');
    return active ? Number(active.dataset.step || 0) : 0;
  }

  function hiddenSelect(kind) { return byId(kind === 'ev' ? 'evSelect' : 'iceSelect'); }
  function trimSelect(kind) { return byId(kind === 'ev' ? 'evTrimSelect' : 'iceTrimSelect'); }
  function searchInput(kind) { return byId(kind === 'ev' ? 'evModelSearch' : 'iceModelSearch'); }

  function ensureOption(select, value, label) {
    if (!select || !value) return;
    if (!Array.from(select.options).some((option) => option.value === value)) {
      const opt = document.createElement('option');
      opt.value = value;
      opt.textContent = label || value;
      select.insertBefore(opt, select.firstChild);
    }
    select.value = value;
  }

  function dispatch(select) {
    if (!select) return;
    try { select.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
    try { select.dispatchEvent(new Event('change', { bubbles: true })); } catch (_) {}
  }

  function findBestFromSearch(kind) {
    const input = searchInput(kind);
    const q = lower(input && input.value);
    if (!q || q.length < 2) return null;
    const list = cars(kind);
    return list.find((car) => {
      const name = lower([car.brand, car.model].filter(Boolean).join(' '));
      return name === q || name.includes(q) || q.includes(name);
    }) || list.find((car) => {
      const name = lower([car.brand, car.model, car.version, car.powertrain].filter(Boolean).join(' '));
      return q.split(/\s+/).filter(Boolean).every((token) => name.includes(token));
    }) || null;
  }

  function selectedCar(kind) {
    const hidden = hiddenSelect(kind);
    const id = hidden && hidden.value;
    if (!id) return null;
    return cars(kind).find((car) => car.id === id) || null;
  }

  function syncKind(kind) {
    const hidden = hiddenSelect(kind);
    if (!hidden) return;

    let car = selectedCar(kind);
    const trim = trimSelect(kind);

    if (!car && trim) {
      let value = trim.value;
      if (!value) {
        const first = Array.from(trim.options).find((option) => option.value);
        if (first) {
          value = first.value;
          trim.value = value;
        }
      }
      if (value) {
        car = cars(kind).find((item) => item.id === value) || null;
        if (car) ensureOption(hidden, car.id, [car.brand, car.model].filter(Boolean).join(' '));
      }
    }

    if (!car) {
      car = findBestFromSearch(kind);
      if (car) ensureOption(hidden, car.id, [car.brand, car.model].filter(Boolean).join(' '));
    }

    if (!car) return;

    dispatch(hidden);

    try { if (typeof setAutoFields === 'function') setAutoFields(); } catch (_) {}
    try { if (typeof calculate === 'function') calculate(); } catch (_) {}
    try { if (typeof drawSummary === 'function') drawSummary(); } catch (_) {}
    try { if (typeof updateNavigation === 'function') updateNavigation(); } catch (_) {}

    try {
      if (typeof renderCarVisual === 'function') {
        renderCarVisual(kind === 'ev' ? 'evVisual' : 'iceVisual', car, kind);
      }
    } catch (_) {}

    try {
      if (typeof renderMiniCar === 'function') {
        renderMiniCar(kind === 'ev' ? 'reportEvVisual' : 'reportIceVisual', car, kind);
      }
    } catch (_) {}
  }

  function syncCarsAndReport() {
    syncKind('ev');
    syncKind('ice');

    try { if (typeof calculate === 'function') calculate(); } catch (_) {}
    try { if (typeof drawSummary === 'function') drawSummary(); } catch (_) {}

    const summary = byId('summaryGrid');
    if (activeStep() === 6 && summary && !clean(summary.textContent)) {
      const msg = document.createElement('div');
      msg.className = 'ios-empty-summary';
      msg.textContent = 'Se il riepilogo è vuoto, torna alle schermate Elettrica e Termica e scegli un modello/allestimento per entrambe le auto.';
      summary.innerHTML = '';
      summary.appendChild(msg);
    }
  }

  function bindSelectionEvents() {
    ['ev', 'ice'].forEach((kind) => {
      [searchInput(kind), trimSelect(kind), hiddenSelect(kind)].forEach((node) => {
        if (!node || node.__iosFinalSelectionBound) return;
        ['input', 'change', 'blur'].forEach((eventName) => {
          node.addEventListener(eventName, () => setTimeout(syncCarsAndReport, 80));
        });
        node.__iosFinalSelectionBound = true;
      });
    });
  }

  function fixChoiceGuideFinish() {
    document.addEventListener('click', (event) => {
      const button = event.target instanceof Element ? event.target.closest('#cgNext') : null;
      if (!button) return;
      const txt = lower(button.textContent);
      if (!txt.includes('report') && !txt.includes('queste auto')) return;
      setTimeout(() => {
        syncCarsAndReport();
        try { if (typeof setStep === 'function') setStep(7); } catch (_) {}
      }, 220);
    }, true);
  }

  function run() {
    bindSelectionEvents();
    syncCarsAndReport();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      fixChoiceGuideFinish();
      run();
    });
  } else {
    fixChoiceGuideFinish();
    run();
  }

  setInterval(run, 600);
})();
