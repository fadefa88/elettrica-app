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
      const node = byId(id);
      if (node) {
        node.hidden = true;
        node.setAttribute('aria-hidden', 'true');
        node.style.display = 'none';
      }
    });
  }

  function run() {
    keepHiddenBoundControls();
    repairTrimSelectors();
  }

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
