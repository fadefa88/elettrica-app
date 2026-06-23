(function(){
  if(window.__motornetUiExtrasLoaded) return;
  window.__motornetUiExtrasLoaded = true;

  function byId(id){ return document.getElementById(id); }
  function num(id){ return Number(byId(id)?.value || 0); }
  function checked(id){ return !!byId(id)?.checked; }
  const euro0 = new Intl.NumberFormat('it-IT', {style:'currency', currency:'EUR', maximumFractionDigits:0});

  function ensureLightbox(){
    let box = byId('carLightbox');
    if(box) return box;
    box = document.createElement('div');
    box.id = 'carLightbox';
    box.className = 'car-lightbox';
    box.hidden = true;
    box.innerHTML = '<button type="button" aria-label="Chiudi immagine">×</button><img alt=""><div class="car-lightbox-caption"></div>';
    document.body.appendChild(box);
    box.addEventListener('click', function(event){
      if(event.target === box || event.target.tagName === 'BUTTON') closeLightbox();
    });
    document.addEventListener('keydown', function(event){ if(event.key === 'Escape') closeLightbox(); });
    return box;
  }

  function openLightbox(img){
    if(!img || !img.src) return;
    const box = ensureLightbox();
    const target = box.querySelector('img');
    const caption = box.querySelector('.car-lightbox-caption');
    target.src = img.currentSrc || img.src;
    target.alt = img.alt || 'Immagine auto';
    caption.textContent = img.alt || '';
    box.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeLightbox(){
    const box = byId('carLightbox');
    if(!box) return;
    box.hidden = true;
    const img = box.querySelector('img');
    if(img) img.removeAttribute('src');
    document.body.style.overflow = '';
  }

  document.addEventListener('click', function(event){
    const img = event.target && event.target.closest ? event.target.closest('img.car-photo') : null;
    if(!img) return;
    event.preventDefault();
    event.stopPropagation();
    openLightbox(img);
  });

  function selectedElectricCar(){
    try { return typeof selectedEv === 'function' ? selectedEv() : null; } catch(e) { return null; }
  }

  function setEvTaxLabel(){
    const checkbox = byId('overrideEvTax');
    if(!checkbox) return;
    const span = checkbox.closest('span');
    if(!span) return;
    span.childNodes.forEach(function(node){ if(node.nodeType === Node.TEXT_NODE) node.nodeValue = ' Override bollo elettrica'; });
  }

  function applyEvTaxPolicy(){
    const years = num('years');
    const input = byId('evTaxAfter5');
    const checkbox = byId('overrideEvTax');
    if(!input || !checkbox) return;
    setEvTaxLabel();
    if(years <= 5){
      checkbox.checked = false;
      checkbox.disabled = true;
      input.value = '0';
      input.readOnly = true;
      input.classList.add('readonly');
      return;
    }
    checkbox.disabled = false;
    if(!checkbox.checked){
      const ev = selectedElectricCar();
      try {
        if(ev && typeof estimateEvTax === 'function'){
          const tax = estimateEvTax(ev);
          if(Number.isFinite(tax)) input.value = String(tax);
        }
      } catch(e) {}
      input.readOnly = true;
      input.classList.add('readonly');
    }else{
      input.readOnly = false;
      input.classList.remove('readonly');
    }
  }

  function evTaxSummaryText(){
    const years = num('years');
    if(years <= 5) return euro0.format(0);
    return euro0.format(num('evTaxAfter5')) + ' all’anno (dal sesto anno)';
  }

  function updateSummaryTaxText(){
    const grid = byId('summaryGrid');
    if(!grid) return;
    grid.querySelectorAll('div').forEach(function(row){
      const label = row.querySelector('small');
      const value = row.querySelector('b');
      if(!label || !value) return;
      if(/bollo\s+elettrica/i.test(label.textContent || '')) value.textContent = evTaxSummaryText() + ' / ' + euro0.format(num('iceTax')) + ' all’anno';
    });
  }

  function pvValid(){ return checked('noPv') || num('solarShare') > 0; }
  function ensurePvHint(){
    let hint = byId('pvRequiredHint');
    if(hint) return hint;
    const screen = document.querySelector('.screen[data-step="5"]');
    if(!screen) return null;
    hint = document.createElement('p');
    hint.id = 'pvRequiredHint';
    hint.className = 'source-note';
    hint.style.marginTop = '10px';
    hint.style.color = '#8a4b00';
    hint.textContent = 'Per proseguire seleziona “Non ho impianto fotovoltaico” oppure indica una quota fotovoltaico maggiore di 0%.';
    const card = screen.querySelector('.card.soft') || screen;
    card.appendChild(hint);
    return hint;
  }

  function updatePvValidation(){
    const hint = ensurePvHint();
    if(hint) hint.hidden = pvValid();
  }

  function removeMotornetBadges(){
    const direct = byId('motornetCatalogBadge') || byId('autoitCatalogBadge');
    if(direct) direct.remove();
    document.querySelectorAll('.app-shell > div').forEach(function(node){
      const text = node.textContent || '';
      if(/Catalogo\s+Motornet\s+(attivo|vuoto)/i.test(text)) node.remove();
    });
  }

  function run(){
    applyEvTaxPolicy();
    updateSummaryTaxText();
    updatePvValidation();
    removeMotornetBadges();
  }

  document.addEventListener('input', function(event){
    const id = event.target && event.target.id;
    if(id && /^(years|overrideEvTax|evTaxAfter5|solarShare|noPv|unknownPv)$/.test(id)) setTimeout(run, 0);
  }, true);
  window.addEventListener('motornet:catalog-ready', function(){ setTimeout(run, 0); });
  window.addEventListener('load', function(){ run(); setTimeout(run, 800); });
  if(document.readyState !== 'loading') setTimeout(run, 0);
  else document.addEventListener('DOMContentLoaded', function(){ setTimeout(run, 0); });
})();
