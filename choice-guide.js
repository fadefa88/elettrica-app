(function(){
  if(window.__choiceGuideLoaded) return;
  window.__choiceGuideLoaded = true;

  let flowStep = 0;
  let state = {budgetMin:20000,budgetMax:35000,km:15000,years:5,home:80,priority:"equilibrio"};
  let evItems=[], iceItems=[], chosenEv=null, chosenIce=null, catalogPromise=null, catalog={EV:[],IC:[]};

  const flowSteps = ["Budget","Percorrenza","Ricarica","Priorità","Scelta"];
  const euro0 = new Intl.NumberFormat("it-IT",{style:"currency",currency:"EUR",maximumFractionDigits:0});
  const euro2 = new Intl.NumberFormat("it-IT",{style:"currency",currency:"EUR",minimumFractionDigits:2,maximumFractionDigits:2});

  function byId(id){return document.getElementById(id)}
  function clean(v){return String(v===null||v===undefined?"":v).replace(/\s+/g," ").trim()}
  function esc(v){return clean(v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]))}
  function num(v,fallback){const x=Number(v);return Number.isFinite(x)?x:fallback}
  function clamp(v,min,max){return Math.max(min,Math.min(max,v))}
  function callGlobal(name){
    try{const fn=window[name] || eval(name); if(typeof fn==="function") return fn()}catch(e){}
  }
  function price(car){return num(car && car.price_eur,0)}
  function kw(car){return num(car && car.power_kw,0)}
  function carName(car){return [clean(car&&car.brand),clean(car&&car.model)].filter(Boolean).join(" ")}
  function carVersion(car){
    const title=carName(car).toLowerCase();
    const v=clean(car && (car.version || car.powertrain));
    return v && v.toLowerCase()!==title ? v : "";
  }
  function isElectric(car){return clean(car&&car.category)==="electric" || /elettr/i.test(clean(car&&car.fuel))}
  function fuelKey(fuel){fuel=clean(fuel).toLowerCase();if(fuel.includes("diesel"))return"gasolio";if(fuel.includes("benzina"))return"benzina";if(fuel.includes("gpl"))return"gpl";if(fuel.includes("metano"))return"metano";return fuel}
  function inBudget(car){const p=price(car),min=Math.min(state.budgetMin,state.budgetMax),max=Math.max(state.budgetMin,state.budgetMax);return p>0&&p>=min&&p<=max}
  async function loadJson(path,fallback){try{const r=await fetch(path+"?v="+Date.now(),{cache:"no-store"});return r.ok?await r.json():fallback}catch(e){return fallback}}
  function fuelPrice(fuel,prices){const key=fuelKey(fuel),table=prices&&prices.fuel?prices.fuel:{},fallback=key==="metano"?1.55:key==="gpl"?.78:key==="gasolio"?1.75:1.85;return num(table[key],fallback)}
  function baseTax(car){const power=kw(car);if(!power)return 0;const bollo=power<=100?power*2.58:100*2.58+(power-100)*3.87;const superbollo=power>185?(power-185)*20:0;return bollo+superbollo}
  function evCost100(car,settings,prices,charging){const consumption=num(car&&car.consumption_kwh_100km,16),homePrice=num(prices&&prices.electricity&&prices.electricity.home,.30),publicPrice=num(charging&&charging.market_average&&charging.market_average.public_mixed,.74),homeShare=clamp(settings.home/100,0,1);return consumption*(homePrice*homeShare+publicPrice*(1-homeShare))}
  function iceCost100(car,prices){const key=fuelKey(car&&car.fuel),consumption=num((car&&car.consumption_kg_100km)||(car&&car.consumption_l_100km),key==="metano"?4:6);return consumption*fuelPrice(car&&car.fuel,prices)}
  function evTco(car,settings,prices,charging){const km=settings.km*settings.years;return price(car)+evCost100(car,settings,prices,charging)*km/100+250*settings.years+(settings.years>5?(settings.years-5)*65:0)}
  function iceTco(car,settings,prices){const km=settings.km*settings.years;return price(car)+iceCost100(car,prices)*km/100+600*settings.years+baseTax(car)*settings.years}
  function score(item,priority){if(priority==="spesa")return item.price;if(priority==="risparmio")return item.tco;if(priority==="autonomia"){const range=isElectric(item.car)?num(item.car&&item.car.range_wltp_km,0):0;return range>0?-range+item.tco/100000:item.tco}if(priority==="potenza")return-kw(item.car)+item.tco/100000;const rangeBonus=isElectric(item.car)?num(item.car&&item.car.range_wltp_km,0)*35:0,powerBonus=kw(item.car)*80;return item.tco*.60+item.price*.30-rangeBonus-powerBonus}
  function priorityLabel(value){return {spesa:"Voglio spendere il meno possibile",risparmio:"Voglio il maggiore risparmio nel tempo",autonomia:"Voglio più autonomia",potenza:"Voglio un’auto più potente",equilibrio:"Voglio il miglior equilibrio"}[value]||"Voglio il miglior equilibrio"}
  function readInputs(){const min=byId("cgBudgetMin"),max=byId("cgBudgetMax"),km=byId("cgKm"),years=byId("cgYears"),home=byId("cgHome"),priority=byId("cgPriority");if(min)state.budgetMin=num(min.value,state.budgetMin);if(max)state.budgetMax=num(max.value,state.budgetMax);if(km)state.km=num(km.value,state.km);if(years)state.years=clamp(num(years.value,state.years),1,20);if(home)state.home=clamp(num(home.value,state.home),0,100);if(priority)state.priority=clean(priority.value)||state.priority}

  function normalizeCatalog(payload){
    const cars=(payload&&payload.cars||[]).filter(c=>c&&clean(c.id)&&clean(c.brand)&&clean(c.model)&&price(c)>0);
    const seenEv=new Set(),seenIc=new Set();
    const EV=cars.filter(c=>isElectric(c)&&!seenEv.has(c.id)&&seenEv.add(c.id)).sort((a,b)=>price(a)-price(b)||carName(a).localeCompare(carName(b),"it"));
    const IC=cars.filter(c=>!isElectric(c)&&!seenIc.has(c.id)&&seenIc.add(c.id)).sort((a,b)=>price(a)-price(b)||carName(a).localeCompare(carName(b),"it"));
    return {EV,IC};
  }
  async function ensureCatalog(){
    if(catalog.EV.length&&catalog.IC.length)return catalog;
    if(catalogPromise)return catalogPromise;
    catalogPromise=(async()=>{
      if(window.__motornetRequestCatalogLoad) try{await window.__motornetRequestCatalogLoad()}catch(e){}
      const payload=await loadJson("data/cars_motornet.json",{cars:[]});
      catalog=normalizeCatalog(payload);
      return catalog;
    })();
    return catalogPromise;
  }
  function listByBudget(list){return list.filter(inBudget)}
  function nearestByBudget(list){
    const min=Math.min(state.budgetMin,state.budgetMax),max=Math.max(state.budgetMin,state.budgetMax),mid=(min+max)/2;
    return list.filter(c=>price(c)>0).sort((a,b)=>Math.abs(price(a)-mid)-Math.abs(price(b)-mid)).slice(0,6);
  }

  function installCss(){
    if(byId("choiceGuideFullscreenStyle")) return;
    const style=document.createElement("style");
    style.id="choiceGuideFullscreenStyle";
    style.textContent=`
      body.choice-guide-fullscreen-open{overflow:hidden}
      .cg-entry{margin-top:24px;padding:20px;border-radius:24px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.22);backdrop-filter:blur(10px);position:relative;z-index:2}
      .cg-entry h3{margin:0 0 6px;color:#f6fff9}.cg-entry p{color:#dbe8e2}.cg-muted{color:#64746d}.cg-actions{display:flex;gap:10px;flex-wrap:wrap}.cg-actions button{box-shadow:0 16px 42px rgba(0,0,0,.16)}
      .cg-page{position:fixed;inset:0;z-index:10000;display:none;overflow:auto;background:linear-gradient(180deg,#f7fbf7,#edf7f1)}
      .cg-page.open{display:block}.cg-shell{max-width:1120px;margin:0 auto;padding:24px}.cg-top{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px}
      .cg-progress{height:8px;border-radius:999px;background:#dfeae3;overflow:hidden}.cg-bar{height:100%;background:#2fc56f;width:20%}.cg-body{background:#fff;border-radius:26px;padding:24px;margin:18px 0;box-shadow:0 20px 60px rgba(20,50,40,.10)}
      .cg-body h1{margin:4px 0 8px}.cg-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:18px}.cg-grid label{font-size:.86rem;color:#50625b}.cg-grid input,.cg-grid select{width:100%;margin-top:6px}
      .cg-budget-hint{margin-top:12px;padding:12px 14px;border-radius:16px;background:#f2f8f4;color:#50625b;font-size:.9rem}.cg-budget-hint.warn{background:#fff4df;color:#6d4b00;border:1px solid #f1d9a8}
      .cg-bottom{display:flex;justify-content:space-between;gap:12px;margin-top:18px}.cg-cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}.cg-card{display:block;width:100%;text-align:left;padding:14px;border-radius:18px;border:1px solid #dfe8e2;background:#fbfdfb;margin-bottom:10px;color:#101817}
      .cg-card.active{border-color:#20b764;box-shadow:0 0 0 3px rgba(32,183,100,.14)}.cg-card small{display:block;color:#6c7c75;text-transform:uppercase;font-size:.7rem}.cg-card b{display:block}.cg-card em{display:block;color:#64746d;font-size:.83rem}
      .cg-card div{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.cg-card span{font-size:.76rem;background:#eef4ef;border-radius:999px;padding:5px 8px}.cg-verdict{padding:14px 16px;border-radius:18px;background:#eef8f1;margin:14px 0}
      @media(max-width:760px){.cg-shell{padding:14px}.cg-grid,.cg-cols{grid-template-columns:1fr}.cg-bottom{position:sticky;bottom:0;background:#edf7f1;padding:10px 0}.cg-actions button{width:100%}}
    `;
    document.head.appendChild(style);
  }
  function ensurePage(){
    if(byId("choiceGuidePage")) return;
    const page=document.createElement("div");
    page.id="choiceGuidePage";page.className="cg-page";
    page.innerHTML=`<div class="cg-shell"><div class="cg-top"><div><b>Scelta guidata</b><div class="cg-muted"><span id="cgStepLabel">1 di 5</span> · <span id="cgStepName">Budget</span></div></div><button id="cgClose" class="ghost" type="button">Torna al comparatore</button></div><div class="cg-progress"><div id="cgProgress" class="cg-bar"></div></div><div id="cgBody" class="cg-body"></div><div class="cg-bottom"><button id="cgPrev" class="ghost" type="button">Indietro</button><button id="cgNext" type="button">Avanti</button></div></div>`;
    document.body.appendChild(page);
    byId("cgClose").onclick=closeGuide;
    byId("cgPrev").onclick=()=>{readInputs();setFlowStep(flowStep-1)};
    byId("cgNext").onclick=()=>{readInputs();if(flowStep===flowSteps.length-1)finishToReport();else setFlowStep(flowStep+1)};
  }
  function openGuide(){flowStep=0;ensurePage();const page=byId("choiceGuidePage");page.classList.add("open");document.body.classList.add("choice-guide-fullscreen-open");renderStep()}
  function closeGuide(){const page=byId("choiceGuidePage");if(!page)return;page.classList.remove("open");document.body.classList.remove("choice-guide-fullscreen-open")}
  function setFlowStep(next){flowStep=clamp(next,0,flowSteps.length-1);renderStep()}
  function updateTop(){const label=byId("cgStepLabel"),name=byId("cgStepName"),bar=byId("cgProgress"),prev=byId("cgPrev"),next=byId("cgNext");if(label)label.textContent=(flowStep+1)+" di "+flowSteps.length;if(name)name.textContent=flowSteps[flowStep];if(bar)bar.style.width=((flowStep+1)/flowSteps.length*100)+"%";if(prev)prev.disabled=flowStep===0;if(next)next.innerHTML=flowStep===flowSteps.length-1?'Usa queste auto e vai al report <i class="fa-solid fa-flag-checkered"></i>':'Avanti <i class="fa-solid fa-arrow-right"></i>'}
  function renderStep(){
    updateTop();const body=byId("cgBody");if(!body)return;
    if(flowStep===0){const min=Math.min(state.budgetMin,state.budgetMax),max=Math.max(state.budgetMin,state.budgetMax);body.innerHTML='<p class="eyebrow">Budget</p><h1>Che fascia di prezzo vuoi considerare?</h1><p class="lead">Imposta un budget minimo e massimo. Se non trovo una coppia completa dentro la fascia, ti propongo comunque le alternative più vicine.</p><div class="cg-grid"><label>Budget minimo €<input id="cgBudgetMin" type="number" value="'+min+'" step="1000"></label><label>Budget massimo €<input id="cgBudgetMax" type="number" value="'+max+'" step="1000"></label></div><div class="cg-budget-hint">Esempio: da 20.000 € a 35.000 €. Il sito privilegia auto dentro questa fascia ma non si blocca se il catalogo ha pochi match.</div>';return}
    if(flowStep===1){body.innerHTML='<p class="eyebrow">Percorrenza</p><h1>Per quanti anni e quanti km?</h1><p class="lead">Questi dati determinano il costo totale reale nel tempo.</p><div class="cg-grid"><label>Km annui<input id="cgKm" type="number" value="'+state.km+'" step="1000"></label><label>Anni di possesso<input id="cgYears" type="number" value="'+state.years+'" min="1" max="20"></label></div>';return}
    if(flowStep===2){body.innerHTML='<p class="eyebrow">Ricarica</p><h1>Come caricheresti l’elettrica?</h1><p class="lead">Più ricarichi a casa, più l’elettrica tende ad avere senso economico.</p><div class="cg-grid"><label>Ricarica a casa %<input id="cgHome" type="number" value="'+state.home+'" min="0" max="100" step="5"></label><label>Scenario rapido<select id="cgHomePreset"><option value="80">Box o presa a casa</option><option value="50">Metà casa, metà colonnine</option><option value="20">Quasi solo colonnine</option></select></label></div>';setTimeout(()=>{const preset=byId("cgHomePreset");if(preset)preset.oninput=()=>{if(byId("cgHome"))byId("cgHome").value=preset.value}},0);return}
    if(flowStep===3){body.innerHTML='<p class="eyebrow">Priorità</p><h1>Cosa vuoi ottimizzare?</h1><p class="lead">Il sito ordina le proposte in base alla logica che scegli qui.</p><div class="cg-grid"><label>Priorità<select id="cgPriority"><option value="spesa">Voglio spendere il meno possibile</option><option value="risparmio">Voglio il maggiore risparmio nel tempo</option><option value="autonomia">Voglio più autonomia</option><option value="potenza">Voglio un’auto più potente</option><option value="equilibrio">Voglio il miglior equilibrio</option></select></label></div><div class="cg-budget-hint">“Miglior equilibrio” pesa insieme prezzo, costo totale, autonomia e potenza.</div>';setTimeout(()=>{if(byId("cgPriority"))byId("cgPriority").value=state.priority},0);return}
    renderChoices();
  }
  function renderCard(item,kind){const car=item.car,selected=kind==="ev"?chosenEv:chosenIce,active=selected&&selected.id===car.id?" active":"",extra=isElectric(car)&&car.range_wltp_km?'<span>'+Math.round(car.range_wltp_km)+' km WLTP</span>':'';return '<button type="button" class="cg-card '+kind+active+'" data-kind="'+kind+'" data-id="'+esc(car.id)+'"><small>'+(kind==="ev"?"Elettrica":"Termica")+'</small><b>'+esc(carName(car))+'</b>'+(carVersion(car)?'<em>'+esc(carVersion(car))+'</em>':'')+'<div><span>Prezzo '+euro0.format(item.price)+'</span><span>TCO '+euro0.format(item.tco)+'</span><span>'+euro2.format(item.cost100)+'/100 km</span>'+extra+'</div></button>'}
  async function renderChoices(){
    const body=byId("cgBody");if(!body)return;body.innerHTML='<p class="eyebrow">Proposte</p><h1>Carico il catalogo…</h1><p class="cg-muted">Un attimo.</p>';
    const cat=await ensureCatalog(),prices=await loadJson("data/prices.json",{fuel:{benzina:1.85,gasolio:1.75,gpl:.78,metano:1.55},electricity:{home:.30}}),charging=await loadJson("data/charging.json",{market_average:{public_mixed:.74}});
    let evSource=listByBudget(cat.EV),iceSource=listByBudget(cat.IC),expanded=false;
    if(!evSource.length){evSource=nearestByBudget(cat.EV);expanded=true}
    if(!iceSource.length){iceSource=nearestByBudget(cat.IC);expanded=true}
    evItems=evSource.map(c=>({car:c,price:price(c),cost100:evCost100(c,state,prices,charging),tco:evTco(c,state,prices,charging)})).sort((a,b)=>score(a,state.priority)-score(b,state.priority)).slice(0,6);
    iceItems=iceSource.map(c=>({car:c,price:price(c),cost100:iceCost100(c,prices),tco:iceTco(c,state,prices)})).sort((a,b)=>score(a,state.priority)-score(b,state.priority)).slice(0,6);
    chosenEv=evItems.some(i=>chosenEv&&i.car.id===chosenEv.id)?chosenEv:(evItems[0]&&evItems[0].car)||null;
    chosenIce=iceItems.some(i=>chosenIce&&i.car.id===chosenIce.id)?chosenIce:(iceItems[0]&&iceItems[0].car)||null;
    const min=Math.min(state.budgetMin,state.budgetMax),max=Math.max(state.budgetMin,state.budgetMax);
    if(!evItems.length&&!iceItems.length){body.innerHTML='<p class="eyebrow">Proposte</p><h1>Catalogo non disponibile.</h1><p class="lead">Non riesco a leggere il catalogo auto. Torna al comparatore classico o ricarica la pagina.</p>';return}
    let verdict="";
    if(evItems[0]&&iceItems[0]){const diff=iceItems[0].tco-evItems[0].tco;verdict='<div class="cg-verdict"><b>'+(diff>=0?"La migliore elettrica costa meno nel periodo indicato.":"La migliore termica costa meno nel periodo indicato.")+'</b><span>Differenza stimata: '+euro0.format(Math.abs(diff))+' in '+state.years+' anni.</span><span>Priorità: '+esc(priorityLabel(state.priority))+'</span></div>'}
    const warn=expanded?'<div class="cg-budget-hint warn">Non ho trovato una coppia completa esattamente nella fascia '+euro0.format(min)+' - '+euro0.format(max)+'. Ti mostro le alternative più vicine per non bloccare la scelta guidata.</div>':'';
    body.innerHTML='<p class="eyebrow">Scelta</p><h1>Scegli una coppia da confrontare.</h1><p class="lead">Fascia budget: '+euro0.format(min)+' - '+euro0.format(max)+'. Dopo il finish arrivi allo stesso report del comparatore classico.</p>'+warn+verdict+'<div class="cg-cols"><section><h3>Elettriche</h3>'+evItems.map(i=>renderCard(i,"ev")).join("")+'</section><section><h3>Termiche</h3>'+iceItems.map(i=>renderCard(i,"ice")).join("")+'</section></div>';
    body.querySelectorAll(".cg-card").forEach(btn=>{btn.onclick=function(){const src=btn.dataset.kind==="ev"?evItems:iceItems,found=src.find(i=>i.car.id===btn.dataset.id);if(found){if(btn.dataset.kind==="ev")chosenEv=found.car;else chosenIce=found.car;renderChoices()}}});
  }
  function setCheck(id,val){const e=byId(id);if(e)e.checked=!!val}
  function setVal(id,val){const e=byId(id);if(e)e.value=val}
  function setHiddenSelect(id,val,label){const e=byId(id);if(!e)return;if(!Array.from(e.options).some(o=>o.value===val))e.insertAdjacentHTML("afterbegin",'<option value="'+esc(val)+'">'+esc(label||val)+'</option>');e.value=val}
  function finishToReport(){
    if(!chosenEv||!chosenIce){alert("Scegli una elettrica e una termica.");return}
    setCheck("manualEvMode",false);setCheck("manualIceMode",false);
    setHiddenSelect("evSelect",chosenEv.id,carName(chosenEv));setHiddenSelect("iceSelect",chosenIce.id,carName(chosenIce));
    setVal("years",state.years);setVal("annualKm",state.km);setVal("homeShare",state.home);
    ["overrideEvPurchase","overridePurchase","overrideFuelPrice","overridePublicCharge","overrideConsumption","overrideEvMaintenance","overrideIceMaintenance","overrideIceTax","overrideEvTax"].forEach(id=>setCheck(id,false));
    callGlobal("setAutoFields");callGlobal("calculate");callGlobal("drawSummary");
    closeGuide();
    try{(window.setStep||eval("setStep"))(7)}catch(e){const next=byId("nextStep"); if(next) next.click()}
  }
  function injectEntry(){
    installCss();ensurePage();
    const hero=document.querySelector('.screen[data-step="0"] .hero-card');
    if(!hero||byId("choiceGuideEntry"))return;
    const entry=document.createElement("div");entry.id="choiceGuideEntry";entry.className="cg-entry";
    entry.innerHTML='<h3>Non hai ancora deciso che auto comprare?</h3><p>Usa una seconda esperienza full-screen: fascia budget, km annui, anni di possesso e abitudini di ricarica. Alla fine arrivi allo stesso report.</p><div class="cg-actions"><button id="cgOpen" type="button">Aiutami a scegliere</button><button id="cgClassic" class="ghost" type="button">Ho già due auto in mente</button></div>';
    hero.appendChild(entry);byId("cgOpen").onclick=openGuide;byId("cgClassic").onclick=function(){const next=byId("nextStep");if(next)next.click()};
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",injectEntry);else injectEntry();
  window.addEventListener("load",injectEntry);
})();
