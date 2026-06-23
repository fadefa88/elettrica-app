(function(){
  if(window.__italianSuperbolloPatchLoaded) return;
  window.__italianSuperbolloPatchLoaded = true;

  const SUPERBOLLO_THRESHOLD_KW = 185;
  const SUPERBOLLO_EUR_PER_KW = 20;
  const euro0 = new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });

  function byId(id){ return document.getElementById(id); }
  function valueNumber(id){ return Number(byId(id)?.value || 0); }
  function checked(id){ return !!byId(id)?.checked; }

  function installAutocompleteScrollGuard(){
    if(window.__motornetAutocompleteScrollGuardInstalled) return;
    window.__motornetAutocompleteScrollGuardInstalled = true;

    const nativeDocumentAdd = document.addEventListener.bind(document);
    const itemSelector = '.motornet-autocomplete-results .motornet-autocomplete-item[data-key]';
    let touchStart = null;
    let lastSafeTapAt = 0;

    document.addEventListener = function(type, listener, options){
      if((type === 'pointerdown' || type === 'touchstart') && typeof listener === 'function'){
        const source = Function.prototype.toString.call(listener);
        if(source.indexOf('ITEM_SELECTOR') >= 0 && source.indexOf('activateAutocompleteItem') >= 0){
          console.info('[motornet] blocked eager autocomplete ' + type + ' handler to allow mobile scrolling');
          return;
        }
      }
      return nativeDocumentAdd(type, listener, options);
    };

    function itemFromEvent(event){
      return event && event.target && event.target.closest ? event.target.closest(itemSelector) : null;
    }

    function blurModelInputSoon(){
      setTimeout(function(){
        const active = document.activeElement;
        if(active && active.classList && active.classList.contains('motornet-model-search')) active.blur();
      }, 30);
    }

    function safeSelect(btn, event){
      if(!btn) return;
      const now = Date.now();
      if(now - lastSafeTapAt < 250) return;
      lastSafeTapAt = now;
      if(event){
        event.preventDefault();
        event.stopPropagation();
      }
      btn.dispatchEvent(new MouseEvent('click', {
        bubbles: true,
        cancelable: true,
        view: window
      }));
      blurModelInputSoon();
    }

    nativeDocumentAdd('touchstart', function(event){
      const btn = itemFromEvent(event);
      if(!btn) return;
      const touch = event.touches && event.touches[0];
      if(!touch) return;
      touchStart = {
        x: touch.clientX,
        y: touch.clientY,
        target: btn,
        time: Date.now()
      };
    }, {capture: true, passive: true});

    nativeDocumentAdd('touchend', function(event){
      if(!touchStart) return;
      const btn = itemFromEvent(event) || touchStart.target;
      const touch = event.changedTouches && event.changedTouches[0];
      if(!btn || !touch){
        touchStart = null;
        return;
      }
      const dx = Math.abs(touch.clientX - touchStart.x);
      const dy = Math.abs(touch.clientY - touchStart.y);
      const dt = Date.now() - touchStart.time;
      const sameItem = btn === touchStart.target || (btn.contains && btn.contains(touchStart.target)) || (touchStart.target.contains && touchStart.target.contains(btn));
      touchStart = null;
      if(sameItem && dx < 10 && dy < 10 && dt < 900) safeSelect(btn, event);
    }, {capture: true, passive: false});

    nativeDocumentAdd('click', function(event){
      const btn = itemFromEvent(event);
      if(btn) blurModelInputSoon();
    }, true);
  }

  installAutocompleteScrollGuard();

  function globalList(name){
    try{
      const list = eval(name);
      return Array.isArray(list) ? list : [];
    }catch(e){
      return [];
    }
  }

  function normalizeSlimRuntimeFields(){
    ['EV','IC'].forEach(function(name){
      globalList(name).forEach(function(car){
        if(!car || typeof car !== 'object') return;
        if(!car.powertrain && car.version) car.powertrain = car.version;
        if(!car.version && car.powertrain) car.version = car.powertrain;
        if(!car.source_url && car.motornet_detail_url) car.source_url = car.motornet_detail_url;
        if(!car.image_url && car.image_local_path) car.image_url = car.image_local_path;
        if(!car.image_url && car.image_source_url) car.image_url = car.image_source_url;
      });
    });
  }

  function cleanMotornetImageCaptionText(value){
    return String(value || '')
      .replace(/\s*Immagine:\s*motornet\.it\s*[·•\-]\s*Motornet/gi, '')
      .replace(/\s*Immagine:\s*motornet\.it/gi, '')
      .replace(/\s*[·•\-]\s*Motornet\s*$/gi, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function textNeedsMotornetCleanup(value){
    return /Immagine:\s*motornet\.it|Motornet/i.test(String(value || ''));
  }

  function cleanValueProperty(el, prop){
    const before = el && el[prop];
    if(!before || !textNeedsMotornetCleanup(before)) return;
    const after = cleanMotornetImageCaptionText(before);
    if(after !== before) el[prop] = after;
  }

  function removeMotornetImageCaptions(){
    if(!document.body) return;

    try{
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const nodes = [];
      let node;
      while((node = walker.nextNode())) nodes.push(node);
      nodes.forEach(function(textNode){
        const before = textNode.nodeValue || '';
        if(!textNeedsMotornetCleanup(before)) return;
        const after = cleanMotornetImageCaptionText(before);
        if(after !== before) textNode.nodeValue = after;
      });
    }catch(e){}

    document.querySelectorAll('[title],[alt],[aria-label]').forEach(function(el){
      ['title','alt','aria-label'].forEach(function(attr){
        const before = el.getAttribute(attr);
        if(!before || !textNeedsMotornetCleanup(before)) return;
        const after = cleanMotornetImageCaptionText(before);
        if(after) el.setAttribute(attr, after);
        else el.removeAttribute(attr);
      });
    });

    document.querySelectorAll('input, textarea, option, select').forEach(function(el){
      cleanValueProperty(el, 'value');
      cleanValueProperty(el, 'textContent');
      cleanValueProperty(el, 'innerText');
    });
  }

  function readPowerKw(car){
    const direct = Number(car && car.power_kw);
    if(Number.isFinite(direct) && direct > 0) return Math.floor(direct);
    const manual = Number(byId('manualIceKw') && byId('manualIceKw').value);
    if(checked('manualIceMode') && Number.isFinite(manual) && manual > 0) return Math.floor(manual);
    return 0;
  }

  function carAgeYears(car){
    const currentYear = new Date().getFullYear();
    const year = Number(car && car.year);
    if(!Number.isFinite(year) || year < 1980 || year > currentYear + 1) return 0;
    return Math.max(0, currentYear - year);
  }

  function superbolloFactorByAge(age){
    if(age >= 20) return 0;
    if(age >= 15) return 0.15;
    if(age >= 10) return 0.30;
    if(age >= 5) return 0.60;
    return 1;
  }

  function superbolloForCar(car){
    const kw = readPowerKw(car);
    if(kw <= SUPERBOLLO_THRESHOLD_KW) return 0;
    const raw = (kw - SUPERBOLLO_THRESHOLD_KW) * SUPERBOLLO_EUR_PER_KW;
    return Math.round(raw * superbolloFactorByAge(carAgeYears(car)));
  }

  function fallbackBaseBollo(car){
    const kw = readPowerKw(car);
    if(!kw) return valueNumber('iceTax') || 0;
    return Math.round(kw <= 100 ? kw * 2.58 : 100 * 2.58 + (kw - 100) * 3.87);
  }

  function selectedThermalCar(){
    try{ if(typeof selectedIce === 'function') return selectedIce(); }catch(e){}
    try{
      const id = byId('iceSelect') && byId('iceSelect').value;
      const list = globalList('IC');
      if(id && list.length) return list.find(function(car){ return car && car.id === id; }) || null;
    }catch(e){}
    return null;
  }

  const originalEstimateIceTax = (typeof estimateIceTax === 'function') ? estimateIceTax : null;

  function baseBolloForCar(car){
    let base = originalEstimateIceTax ? Number(originalEstimateIceTax(car)) : fallbackBaseBollo(car);
    if(!Number.isFinite(base) || base < 0) base = fallbackBaseBollo(car);
    return Math.round(base);
  }

  function totalTaxForCar(car){
    const base = baseBolloForCar(car);
    const extra = superbolloForCar(car);
    if(car){
      car.__base_bollo_tax_eur = base;
      car.__superbollo_tax_eur = extra;
      car.__total_bollo_tax_eur = base + extra;
    }
    return Math.round(base + extra);
  }

  function patchedEstimateIceTax(car){
    return totalTaxForCar(car);
  }

  try{
    estimateIceTax = patchedEstimateIceTax;
    window.estimateIceTax = patchedEstimateIceTax;
  }catch(e){
    window.estimateIceTax = patchedEstimateIceTax;
  }

  function updateIceTaxLabel(){
    const checkbox = byId('overrideIceTax');
    if(!checkbox) return;
    const span = checkbox.closest('span');
    if(!span) return;
    const car = selectedThermalCar();
    const extra = superbolloForCar(car);
    span.childNodes.forEach(function(node){
      if(node.nodeType === Node.TEXT_NODE){
        node.nodeValue = extra > 0 ? ' Override bollo + superbollo termica' : ' Override bollo termica';
      }
    });
  }

  function updateIceTaxField(){
    const car = selectedThermalCar();
    const input = byId('iceTax');
    if(!input || !car) return;
    updateIceTaxLabel();
    if(!checked('overrideIceTax')){
      input.value = String(totalTaxForCar(car));
      input.readOnly = true;
      input.classList.add('readonly');
    }
  }

  function updateSummaryText(){
    const grid = byId('summaryGrid');
    const car = selectedThermalCar();
    if(!grid || !car) return;
    const extra = superbolloForCar(car);
    const total = valueNumber('iceTax');
    const base = Math.max(0, total - extra);

    grid.querySelectorAll('div').forEach(function(row){
      const label = row.querySelector('small');
      const value = row.querySelector('b');
      if(!label || !value) return;
      if(/bollo\s+elettrica/i.test(label.textContent || '')){
        const ev = value.textContent.split('/')[0].trim();
        const ice = extra > 0
          ? euro0.format(total) + ' all’anno (bollo ' + euro0.format(base) + ' + superbollo ' + euro0.format(extra) + ')'
          : euro0.format(total) + ' all’anno';
        value.textContent = ev + ' / ' + ice;
      }
    });
  }

  function updateFootnote(){
    const note = byId('costsFootnote');
    const car = selectedThermalCar();
    if(!note || !car) return;
    const extra = superbolloForCar(car);
    if(extra > 0){
      note.textContent = '* Manutenzione e bollo sono stime da verificare. Per questa termica è incluso anche il superbollo: ' + euro0.format(extra) + ' annui stimati perché supera ' + SUPERBOLLO_THRESHOLD_KW + ' kW.';
    }
  }

  function run(){
    normalizeSlimRuntimeFields();
    updateIceTaxField();
    updateSummaryText();
    updateFootnote();
    removeMotornetImageCaptions();
  }

  if(typeof setAutoFields === 'function'){
    const originalSetAutoFields = setAutoFields;
    setAutoFields = function(){
      normalizeSlimRuntimeFields();
      const result = originalSetAutoFields.apply(this, arguments);
      run();
      return result;
    };
    window.setAutoFields = setAutoFields;
  }

  if(typeof calculate === 'function'){
    const originalCalculate = calculate;
    calculate = function(){
      normalizeSlimRuntimeFields();
      updateIceTaxField();
      const result = originalCalculate.apply(this, arguments);
      run();
      return result;
    };
    window.calculate = calculate;
  }

  if(typeof drawSummary === 'function'){
    const originalDrawSummary = drawSummary;
    drawSummary = function(){
      normalizeSlimRuntimeFields();
      const result = originalDrawSummary.apply(this, arguments);
      run();
      return result;
    };
    window.drawSummary = drawSummary;
  }

  document.addEventListener('change', function(event){
    if(['iceSelect','manualIceMode','manualIceKw','manualIceFuel','overrideIceTax','years'].includes(event.target && event.target.id)){
      setTimeout(function(){
        run();
        try{ if(typeof calculate === 'function') calculate(); }catch(e){}
      }, 0);
    }
  }, true);

  document.addEventListener('input', function(event){
    if(['manualIceKw','overrideIceTax','iceTax'].includes(event.target && event.target.id)){
      setTimeout(function(){
        run();
        try{ if(typeof calculate === 'function') calculate(); }catch(e){}
      }, 0);
    }
  }, true);

  window.addEventListener('load', function(){
    run();
    let count = 0;
    const timer = setInterval(function(){
      run();
      count += 1;
      if(count >= 20) clearInterval(timer);
    }, 300);
  });
})();
