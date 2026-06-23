(function(){
  const POLL_MS = 500;
  const MAX_POLLS = 30;
  const MAX_RESULTS = 25;
  let installed = false;
  let lastEvGroupKey = '';
  let lastIceGroupKey = '';
  const groupCache = {ev: new Map(), ice: new Map()};

  function byId(id){ return document.getElementById(id); }
  function clean(value){ return String(value || '').replace(/\bundefined\b/gi, '').replace(/\s+/g, ' ').trim(); }
  function esc(value){
    return clean(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function money(value){
    const n = Number(value || 0);
    return n > 0 ? new Intl.NumberFormat('it-IT', {style:'currency', currency:'EUR', maximumFractionDigits:0}).format(n) : '';
  }
  function fuelLabelLocal(fuel){
    try { if(typeof fuelLabel === 'function') return fuelLabel(fuel); } catch(e) {}
    return ({benzina:'Benzina', diesel:'Diesel', gasolio:'Diesel', gpl:'GPL', metano:'Metano', elettrica:'Elettrica', elettrica_idrogeno:'Elettrica a idrogeno', ibrida_benzina:'Ibrida benzina', ibrida_diesel:'Ibrida diesel', ibrida_gpl:'Ibrida GPL', ibrida_metano:'Ibrida metano'}[fuel] || fuel || '');
  }
  function carArray(kind){
    return kind === 'ev' ? (Array.isArray(EV) ? EV : []) : (Array.isArray(IC) ? IC : []);
  }
  function clearGroupCache(kind){
    if(kind) groupCache[kind].clear();
    else { groupCache.ev.clear(); groupCache.ice.clear(); }
  }
  function modelId(car){
    const text = [car && car.source_url, car && car.motornet_detail_url].join(' ');
    const m = text.match(/\/modello\/(\d+)/i);
    if(m) return m[1];
    return clean([car && car.brand, car && car.model].join('|')).toLowerCase();
  }
  function trimCode(car){
    const text = [car && car.source_url, car && car.motornet_detail_url].join(' ');
    const m = text.match(/\/allestimento\/([A-Z0-9]+)/i);
    return m ? m[1].toUpperCase() : clean(car && car.id);
  }
  function words(text){ return clean(text).split(' ').filter(Boolean); }
  function commonPrefix(models){
    const lists = models.map(words).filter(a => a.length);
    if(!lists.length) return '';
    const out = [];
    for(let i=0; i<lists[0].length; i++){
      const w = lists[0][i];
      if(lists.every(a => clean(a[i]).toLowerCase() === clean(w).toLowerCase())) out.push(w);
      else break;
    }
    return clean(out.join(' '));
  }
  function modelText(car){
    const brand = clean(car && car.brand);
    let model = clean(car && car.model);
    if(brand && model.toLowerCase().startsWith(brand.toLowerCase() + ' ')) model = clean(model.slice(brand.length));
    return model || clean(car && car.version) || clean(car && car.powertrain) || 'Modello Motornet';
  }
  function groupLabel(cars){
    const models = cars.map(modelText).filter(Boolean);
    if(cars.length > 1){
      const prefix = commonPrefix(models);
      if(prefix) return prefix;
    }
    return models[0] || 'Modello Motornet';
  }
  function suffixLabel(car, baseLabel){
    const model = modelText(car);
    let suffix = model;
    const b = clean(baseLabel);
    if(b && suffix.toLowerCase().startsWith(b.toLowerCase())) suffix = clean(suffix.slice(b.length));
    if(!suffix) suffix = clean(car.version || car.powertrain || trimCode(car));
    if(b && suffix.toLowerCase().startsWith(b.toLowerCase())) suffix = clean(suffix.slice(b.length));
    if(!suffix || suffix.toLowerCase() === clean(car.brand).toLowerCase()) suffix = 'Allestimento base';
    const parts = [suffix];
    if(car.fuel) parts.push(fuelLabelLocal(car.fuel));
    if(car.year) parts.push(String(car.year));
    const p = money(car.price_eur || car.price);
    if(p) parts.push(p);
    return parts.filter(Boolean).join(' · ');
  }
  function groupMeta(g){
    const fuels = Array.from(new Set(g.cars.map(c => fuelLabelLocal(c.fuel)).filter(Boolean))).slice(0, 3).join(', ');
    const prices = g.cars.map(c => Number(c.price_eur || c.price || 0)).filter(n => n > 0);
    const minPrice = prices.length ? Math.min.apply(null, prices) : 0;
    const p = minPrice ? 'da ' + money(minPrice) : '';
    return [g.cars.length + ' all.', fuels, p].filter(Boolean).join(' · ');
  }
  function currentFilter(kind){
    const fuelId = kind === 'ev' ? 'evFuelPick' : 'iceFuelPick';
    const brandId = kind === 'ev' ? 'evBrandPick' : 'iceBrandPick';
    return {
      fuel: byId(fuelId)?.value || 'all',
      brand: byId(brandId)?.value || 'all'
    };
  }
  function filteredCars(kind){
    const f = currentFilter(kind);
    return carArray(kind).filter(c => (f.fuel === 'all' || c.fuel === f.fuel) && (f.brand === 'all' || c.brand === f.brand));
  }
  function buildGroups(cars){
    const map = new Map();
    cars.forEach(car => {
      const key = modelId(car);
      if(!map.has(key)) map.set(key, {key, cars: []});
      map.get(key).cars.push(car);
    });
    const groups = Array.from(map.values()).map(g => {
      g.cars.sort((a,b) => (Number(a.price_eur||0) - Number(b.price_eur||0)) || clean(a.model).localeCompare(clean(b.model), 'it'));
      g.label = groupLabel(g.cars);
      g.brand = clean(g.cars[0] && g.cars[0].brand);
      g.search = clean([g.brand, g.label, ...g.cars.slice(0, 8).map(c => [c.model, c.version, c.powertrain].join(' '))].join(' ')).toLowerCase();
      return g;
    });
    groups.sort((a,b) => (a.brand + ' ' + a.label).localeCompare((b.brand + ' ' + b.label), 'it'));
    return groups;
  }
  function cacheKey(kind){
    const f = currentFilter(kind);
    const arr = carArray(kind);
    const last = arr.length ? arr[arr.length - 1].id : '';
    return [kind, f.fuel, f.brand, arr.length, last].join('|');
  }
  function getGroups(kind){
    const key = cacheKey(kind);
    if(groupCache[kind].has(key)) return groupCache[kind].get(key);
    const groups = buildGroups(filteredCars(kind));
    groupCache[kind].set(key, groups);
    return groups;
  }
  function selectedGroupKey(kind){ return kind === 'ev' ? lastEvGroupKey : lastIceGroupKey; }
  function setSelectedGroupKey(kind, value){ if(kind === 'ev') lastEvGroupKey = value || ''; else lastIceGroupKey = value || ''; }
  function hiddenId(kind){ return kind === 'ev' ? 'evSelect' : 'iceSelect'; }
  function inputId(kind){ return kind === 'ev' ? 'evModelSearch' : 'iceModelSearch'; }
  function resultId(kind){ return kind === 'ev' ? 'evModelResults' : 'iceModelResults'; }
  function trimId(kind){ return kind === 'ev' ? 'evTrimSelect' : 'iceTrimSelect'; }
  function trimWrapId(kind){ return kind === 'ev' ? 'evTrimWrap' : 'iceTrimWrap'; }
  function hintId(kind){ return kind === 'ev' ? 'evChoiceHint' : 'iceChoiceHint'; }

  function ensureEvFuelSelect(){
    if(byId('evFuelPick')) return;
    const brand = byId('evBrandPick');
    if(!brand) return;
    const brandLabel = brand.closest('label');
    const label = document.createElement('label');
    label.innerHTML = 'Alimentazione elettrica<select id="evFuelPick"><option value="all">Tutte</option></select>';
    if(brandLabel && brandLabel.parentNode) brandLabel.parentNode.insertBefore(label, brandLabel);
  }
  function refreshFuelOptions(kind){
    const el = byId(kind === 'ev' ? 'evFuelPick' : 'iceFuelPick');
    if(!el) return;
    const current = el.value || 'all';
    const fuels = Array.from(new Set(carArray(kind).map(c => c.fuel).filter(Boolean))).sort((a,b) => fuelLabelLocal(a).localeCompare(fuelLabelLocal(b), 'it'));
    el.innerHTML = '<option value="all">Tutte</option>' + fuels.map(f => '<option value="'+esc(f)+'">'+esc(fuelLabelLocal(f))+'</option>').join('');
    el.value = fuels.includes(current) ? current : 'all';
  }
  function ensureSmartSelector(oldSelectId, kind, searchLabelText, trimLabelText, full){
    const old = byId(oldSelectId);
    if(!old || byId(inputId(kind))) return;
    const oldLabel = old.closest('label');
    if(oldLabel) oldLabel.style.display = 'none';
    old.style.display = 'none';

    const searchLabel = document.createElement('label');
    searchLabel.className = (full ? 'full ' : '') + 'motornet-smart-model-label';
    searchLabel.innerHTML = searchLabelText + '<input id="'+inputId(kind)+'" class="motornet-model-search" autocomplete="off" placeholder="Scrivi marca o modello, es. Model Y, X3, Panda"><div id="'+resultId(kind)+'" class="motornet-autocomplete-results" hidden></div>';

    const trimLabel = document.createElement('label');
    trimLabel.id = trimWrapId(kind);
    trimLabel.className = (full ? 'full ' : '') + 'motornet-trim-label';
    trimLabel.style.display = 'none';
    trimLabel.innerHTML = trimLabelText + '<select id="'+trimId(kind)+'"></select>';

    const anchor = oldLabel || old;
    anchor.parentNode.insertBefore(searchLabel, anchor.nextSibling);
    searchLabel.parentNode.insertBefore(trimLabel, searchLabel.nextSibling);
  }
  function emitNativeChange(el){
    if(!el) return;
    try { el.dispatchEvent(new Event('input', {bubbles:true})); } catch(e) {}
    try { el.dispatchEvent(new Event('change', {bubbles:true})); } catch(e) {}
  }
  function setHiddenSelection(kind, carId){
    const hidden = byId(hiddenId(kind));
    if(!hidden) return;
    hidden.innerHTML = carId ? '<option value="'+esc(carId)+'" selected>'+esc(carId)+'</option>' : '<option value=""></option>';
    hidden.value = carId || '';
    emitNativeChange(hidden);
  }
  function clearSelection(kind, keepInput, runCalc){
    const input = byId(inputId(kind));
    const results = byId(resultId(kind));
    const trim = byId(trimId(kind));
    const wrap = byId(trimWrapId(kind));
    setSelectedGroupKey(kind, '');
    setHiddenSelection(kind, '');
    if(!keepInput && input) input.value = '';
    if(results){ results.innerHTML = ''; results.hidden = true; }
    if(trim) trim.innerHTML = '<option value="">Prima scegli il modello</option>';
    if(wrap) wrap.style.display = 'none';
    if(runCalc !== false) runAfterSelection();
  }
  function userIsTyping(kind){
    const input = byId(inputId(kind));
    return !!(input && document.activeElement === input && clean(input.value));
  }
  function renderResults(kind){
    const input = byId(inputId(kind));
    const box = byId(resultId(kind));
    const hint = byId(hintId(kind));
    if(!input || !box) return;
    const q = clean(input.value).toLowerCase();
    const groups = getGroups(kind);
    if(hint) hint.textContent = groups.length ? '' : 'Nessuna auto Motornet disponibile per questo filtro.';
    if(q.length < 2){
      box.innerHTML = '<div class="motornet-autocomplete-empty">Scrivi almeno 2 caratteri per cercare il modello.</div>';
      box.hidden = false;
      return;
    }
    const tokens = q.split(/\s+/).filter(Boolean);
    const matches = groups.filter(g => tokens.every(t => g.search.includes(t))).slice(0, MAX_RESULTS);
    if(!matches.length){
      box.innerHTML = '<div class="motornet-autocomplete-empty">Nessun modello trovato con questi filtri.</div>';
      box.hidden = false;
      return;
    }
    box.innerHTML = matches.map(g => '<button type="button" class="motornet-autocomplete-item" data-key="'+esc(g.key)+'"><b>'+esc([g.brand, g.label].filter(Boolean).join(' '))+'</b><span>'+esc(groupMeta(g))+'</span></button>').join('');
    box.hidden = false;
    Array.from(box.querySelectorAll('button[data-key]')).forEach(btn => {
      btn.addEventListener('click', function(){ selectGroup(kind, btn.getAttribute('data-key')); });
    });
  }
  function selectGroup(kind, key){
    const groups = getGroups(kind);
    const group = groups.find(g => g.key === key);
    const input = byId(inputId(kind));
    const box = byId(resultId(kind));
    if(!group){ clearSelection(kind, true); return; }
    setSelectedGroupKey(kind, key);
    if(input) input.value = [group.brand, group.label].filter(Boolean).join(' ');
    if(box){ box.innerHTML = ''; box.hidden = true; }
    fillTrim(kind, true);
  }
  function fillTrim(kind, resetSelection){
    const groups = getGroups(kind);
    const key = selectedGroupKey(kind);
    const group = groups.find(g => g.key === key);
    const trim = byId(trimId(kind));
    const wrap = byId(trimWrapId(kind));
    const hidden = byId(hiddenId(kind));
    if(!trim || !hidden) return;
    const current = resetSelection ? '' : hidden.value;
    if(!group){
      if(wrap) wrap.style.display = 'none';
      trim.innerHTML = '<option value="">Prima scegli il modello</option>';
      setHiddenSelection(kind, '');
      runAfterSelection();
      return;
    }
    if(wrap) wrap.style.display = '';
    trim.innerHTML = '<option value="">Seleziona allestimento</option>' + group.cars.map(c => '<option value="'+esc(c.id)+'">'+esc(suffixLabel(c, group.label))+'</option>').join('');
    let next = group.cars.some(c => c.id === current) ? current : '';
    if(!next && group.cars.length === 1) next = group.cars[0].id;
    trim.value = next;
    setHiddenSelection(kind, next);
    runAfterSelection();
  }
  function refreshSmart(kind){
    clearGroupCache(kind);
    const groups = getGroups(kind);
    const currentId = byId(hiddenId(kind))?.value || '';
    const currentGroup = groups.find(g => g.cars.some(c => c.id === currentId));
    const input = byId(inputId(kind));
    if(currentGroup){
      setSelectedGroupKey(kind, currentGroup.key);
      if(input && !userIsTyping(kind)) input.value = [currentGroup.brand, currentGroup.label].filter(Boolean).join(' ');
      fillTrim(kind, false);
    } else if(userIsTyping(kind)){
      setSelectedGroupKey(kind, '');
      setHiddenSelection(kind, '');
      const trim = byId(trimId(kind));
      const wrap = byId(trimWrapId(kind));
      if(trim) trim.innerHTML = '<option value="">Prima scegli il modello</option>';
      if(wrap) wrap.style.display = 'none';
    } else {
      clearSelection(kind, false);
    }
    const hint = byId(hintId(kind));
    if(hint) hint.textContent = groups.length ? '' : 'Nessuna auto Motornet disponibile per questo filtro.';
  }
  function runAfterSelection(){
    if(typeof setAutoFields === 'function') setAutoFields();
    if(typeof calculate === 'function') calculate();
    if(typeof updateNavigation === 'function') updateNavigation();
  }
  function syncManual(){
    const evOn = !!byId('manualEvMode')?.checked;
    const iceOn = !!byId('manualIceMode')?.checked;
    ['evModelSearch','evTrimSelect'].forEach(id => { const el = byId(id); if(el) el.disabled = evOn; });
    ['iceModelSearch','iceTrimSelect'].forEach(id => { const el = byId(id); if(el) el.disabled = iceOn; });
  }
  function injectStyles(){
    if(byId('motornetSmartSelectorStyles')) return;
    const style = document.createElement('style');
    style.id = 'motornetSmartSelectorStyles';
    style.textContent = `
      .motornet-smart-model-label{position:relative;}
      .motornet-model-search{width:100%;}
      .motornet-autocomplete-results{position:absolute;left:0;right:0;top:calc(100% + 6px);z-index:80;max-height:320px;overflow:auto;background:var(--card-bg,#fff);border:1px solid rgba(120,120,120,.25);border-radius:14px;box-shadow:0 18px 45px rgba(0,0,0,.18);padding:6px;}
      .motornet-autocomplete-item{width:100%;display:flex;flex-direction:column;gap:3px;text-align:left;background:transparent;border:0;border-radius:10px;padding:10px 12px;cursor:pointer;color:inherit;}
      .motornet-autocomplete-item:hover,.motornet-autocomplete-item:focus{background:rgba(120,120,120,.12);outline:none;}
      .motornet-autocomplete-item b{font-size:.95rem;line-height:1.2;}
      .motornet-autocomplete-item span,.motornet-autocomplete-empty{font-size:.78rem;opacity:.72;}
      .motornet-autocomplete-empty{padding:10px 12px;}
    `;
    document.head.appendChild(style);
  }
  function wire(){
    injectStyles();
    ensureEvFuelSelect();
    refreshFuelOptions('ev');
    refreshFuelOptions('ice');
    ensureSmartSelector('evSelect', 'ev', 'Modello elettrica', 'Allestimento elettrica', false);
    ensureSmartSelector('iceSelect', 'ice', 'Modello termica', 'Allestimento termica', true);

    ['ev','ice'].forEach(kind => {
      const input = byId(inputId(kind));
      const trim = byId(trimId(kind));
      if(input && !input.__motornetSmartBound){
        input.addEventListener('input', function(){
          setSelectedGroupKey(kind, '');
          setHiddenSelection(kind, '');
          const wrap = byId(trimWrapId(kind));
          if(wrap) wrap.style.display = 'none';
          renderResults(kind);
        });
        input.addEventListener('focus', function(){ renderResults(kind); });
        input.__motornetSmartBound = true;
      }
      if(trim && !trim.__motornetSmartBound){
        const onTrimPick = function(){ setHiddenSelection(kind, trim.value); runAfterSelection(); };
        trim.addEventListener('input', onTrimPick);
        trim.addEventListener('change', onTrimPick);
        trim.__motornetSmartBound = true;
      }
    });

    try {
      fillEvSelect = function(){ refreshFuelOptions('ev'); refreshSmart('ev'); };
      fillIceSelect = function(){ refreshFuelOptions('ice'); refreshSmart('ice'); };
    } catch(e) {}

    const evBrand = byId('evBrandPick');
    if(evBrand) evBrand.oninput = function(){ refreshSmart('ev'); };
    const evFuel = byId('evFuelPick');
    if(evFuel) evFuel.oninput = function(){ if(typeof fillEvBrands === 'function') fillEvBrands(); refreshSmart('ev'); };
    const iceFuel = byId('iceFuelPick');
    if(iceFuel) iceFuel.oninput = function(){ refreshSmart('ice'); };
    const iceBrand = byId('iceBrandPick');
    if(iceBrand) iceBrand.oninput = function(){ refreshSmart('ice'); };

    document.addEventListener('click', function(e){
      ['ev','ice'].forEach(kind => {
        const input = byId(inputId(kind));
        const box = byId(resultId(kind));
        if(box && input && !box.contains(e.target) && e.target !== input) box.hidden = true;
      });
    }, {capture:true});

    ['manualEvMode','manualIceMode'].forEach(id => {
      const el = byId(id);
      if(el && !el.__motornetSmartManualBound){ el.addEventListener('input', syncManual); el.__motornetSmartManualBound = true; }
    });
    syncManual();
  }
  function init(){
    if(installed) return true;
    if(typeof EV === 'undefined' || typeof IC === 'undefined') return false;
    if(!byId('evSelect') || !byId('iceSelect')) return false;
    wire();
    if(typeof fillEvSelect === 'function') fillEvSelect();
    if(typeof fillIceSelect === 'function') fillIceSelect();
    installed = true;
    return true;
  }
  function startInitPolling(){
    let n = 0;
    const timer = setInterval(function(){
      n += 1;
      if(init()) clearInterval(timer);
      if(n >= 12) clearInterval(timer);
    }, 250);
  }

  window.addEventListener('motornet:catalog-ready', function(){ init(); });
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startInitPolling);
  else startInitPolling();
  window.addEventListener('load', startInitPolling);
})();
