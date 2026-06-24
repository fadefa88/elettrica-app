(function(){
  const STORAGE_KEY='eot_cookie_choice';
  const START_YEAR=2026;
  const SITE_NAME='Elettrica o Termica';
  const SITE_URL='elettricaotermica.it';
  let localJsPdfPromise=null;

  function byId(id){return document.getElementById(id)}
  function clean(v){return String(v||'').replace(/\s+/g,' ').trim()}
  function text(sel,fallback){const el=document.querySelector(sel);return clean(el&&el.textContent)||fallback||''}
  function currentYearLabel(){const y=new Date().getFullYear();return y<=START_YEAR?String(START_YEAR):START_YEAR+'-'+y}
  function isNativeApp(){return !!(window.Capacitor && (window.Capacitor.isNativePlatform?.() || window.Capacitor.getPlatform?.()==='ios'))}

  function saveChoice(choice){
    try{localStorage.setItem(STORAGE_KEY,choice)}catch(e){}
    const banner=byId('cookieBanner');
    if(banner) banner.classList.remove('is-visible');
    if(choice==='accepted' && typeof window.EOT_ENABLE_ANALYTICS==='function') window.EOT_ENABLE_ANALYTICS();
  }

  function readChoice(){try{return localStorage.getItem(STORAGE_KEY)}catch(e){return null}}

  function showBanner(){
    if(isNativeApp()) return;
    if(byId('cookieBanner')) return;
    const banner=document.createElement('div');
    banner.id='cookieBanner';
    banner.className='cookie-banner';
    banner.setAttribute('role','dialog');
    banner.setAttribute('aria-label','Preferenze cookie');
    banner.innerHTML='<p><b>Cookie e analytics</b>Usiamo solo cookie tecnici e, se accetti, analytics aggregati. <a href="/privacy.html">Leggi privacy e cookie</a>.</p><div class="cookie-actions"><button type="button" class="ghost" data-cookie-choice="rejected">Rifiuta</button><button type="button" data-cookie-choice="accepted">Accetta analytics</button></div>';
    document.body.appendChild(banner);
    banner.addEventListener('click',function(ev){const btn=ev.target.closest('[data-cookie-choice]'); if(btn) saveChoice(btn.getAttribute('data-cookie-choice'))});
    setTimeout(function(){banner.classList.add('is-visible')},250);
  }

  function installFooter(){
    if(isNativeApp()) return;
    const shell=document.querySelector('.app-shell');
    if(!shell || document.querySelector('.site-footer')) return;
    const footer=document.createElement('footer');
    footer.className='site-footer';
    footer.innerHTML='<div class="footer-brand"><span class="copyright-icon">©</span><span><span data-footer-years>'+currentYearLabel()+'</span> '+SITE_NAME+' · '+SITE_URL+'</span></div><div class="footer-links"><a href="/">Calcolatore</a><a href="/guida.html">Guida</a><a href="/metodologia.html">Metodologia</a><a href="/privacy.html">Privacy</a></div>';
    shell.appendChild(footer);
  }

  function installSafeMobileInputPolish(){
    const viewport=document.querySelector('meta[name="viewport"]');
    if(viewport && isNativeApp()) viewport.setAttribute('content','width=device-width,initial-scale=1,viewport-fit=cover');
    if(byId('eotSafeMobileInputCss')) return;
    const style=document.createElement('style');
    style.id='eotSafeMobileInputCss';
    style.textContent='input,select,textarea{font-size:16px!important}';
    document.head.appendChild(style);
  }

  async function loadLocalJsPdf(){
    if(window.jspdf&&window.jspdf.jsPDF) return true;
    if(localJsPdfPromise) return localJsPdfPromise;
    localJsPdfPromise=new Promise(function(resolve){
      const script=document.createElement('script');
      script.src='vendor/jspdf.umd.min.js';
      script.onload=function(){resolve(!!(window.jspdf&&window.jspdf.jsPDF))};
      script.onerror=function(){resolve(false)};
      document.head.appendChild(script);
    });
    return localJsPdfPromise;
  }

  async function saveOrSharePdf(doc,fileName){
    if(isNativeApp()){
      const plugins=window.Capacitor?.Plugins||{};
      const Filesystem=plugins.Filesystem;
      const Share=plugins.Share;
      if(Filesystem&&Share){
        try{
          const dataUri=doc.output('datauristring');
          const base64=String(dataUri||'').split(',')[1]||'';
          if(base64){
            const safePath=(fileName||'report-elettricaotermica.pdf').replace(/[^a-zA-Z0-9_.-]/g,'-');
            await Filesystem.writeFile({path:safePath,data:base64,directory:'CACHE',recursive:true});
            const uriResult=await Filesystem.getUri({path:safePath,directory:'CACHE'});
            await Share.share({title:'Report Elettrica o Termica',text:'Report PDF del confronto auto.',url:uriResult.uri,dialogTitle:'Esporta PDF'});
            return;
          }
        }catch(e){
          console.warn('Native PDF export failed',e);
          alert('PDF generato, ma non sono riuscito ad aprire la condivisione iOS. Riprova o usa Copia riepilogo.');
          return;
        }
      }
    }
    doc.save(fileName||'report-elettricaotermica.pdf');
  }

  async function imageToJpegDataUrl(input){
    return new Promise(async function(resolve){
      let src='';
      if(!input) return resolve(null);
      if(typeof input==='string') src=input;
      else src=input.currentSrc || input.src || input.getAttribute?.('src') || '';
      if(!src) return resolve(null);

      function drawUrl(url){
        return new Promise(function(done){
          const img=new Image();
          img.crossOrigin='anonymous';
          img.onload=function(){
            try{
              const canvas=document.createElement('canvas');
              const maxW=900;
              const ratio=Math.min(1,maxW/img.naturalWidth);
              canvas.width=Math.max(1,Math.round(img.naturalWidth*ratio));
              canvas.height=Math.max(1,Math.round(img.naturalHeight*ratio));
              const ctx=canvas.getContext('2d');
              ctx.fillStyle='#f7faf8';
              ctx.fillRect(0,0,canvas.width,canvas.height);
              ctx.drawImage(img,0,0,canvas.width,canvas.height);
              done(canvas.toDataURL('image/jpeg',0.9));
            }catch(e){done(null)}
          };
          img.onerror=function(){done(null)};
          img.src=url;
        });
      }

      try{
        const absolute=new URL(src,location.href).href;
        try{
          const response=await fetch(absolute,{cache:'no-store'});
          if(response.ok){
            const blob=await response.blob();
            const objectUrl=URL.createObjectURL(blob);
            const data=await drawUrl(objectUrl);
            URL.revokeObjectURL(objectUrl);
            if(data) return resolve(data);
          }
        }catch(e){}
        const direct=await drawUrl(absolute);
        return resolve(direct);
      }catch(e){return resolve(null)}
    });
  }

  function addWrappedText(doc,value,x,y,maxWidth,lineHeight){
    const lines=doc.splitTextToSize(String(value||''),maxWidth);
    lines.forEach(function(line){doc.text(line,x,y);y+=lineHeight});
    return y;
  }

  async function enhancedPdf(){
    await loadLocalJsPdf();
    const jsPDF=window.jspdf&&window.jspdf.jsPDF;
    if(!jsPDF){alert('Libreria PDF non disponibile.');return}
    const saving=text('#savingTotal','-');
    if(!saving || saving==='-'){alert('Genera prima il risultato finale.');return}

    const evName=text('#reportEvVisual b','Auto elettrica scelta');
    const iceName=text('#reportIceVisual b','Auto termica scelta');
    const evImg=document.querySelector('#reportEvVisual img.car-photo');
    const iceImg=document.querySelector('#reportIceVisual img.car-photo');
    const logo=await imageToJpegDataUrl('/assets/logopippo.png');
    const evPhoto=await imageToJpegDataUrl(evImg);
    const icePhoto=await imageToJpegDataUrl(iceImg);

    const doc=new jsPDF({unit:'mm',format:'a4'});
    doc.setFillColor(7,17,14);doc.rect(0,0,210,64,'F');
    doc.setFillColor(12,59,40);doc.roundedRect(10,10,190,44,8,8,'F');
    if(logo) doc.addImage(logo,'JPEG',16,15,20,20);
    doc.setTextColor(245,255,249);doc.setFont('helvetica','bold');doc.setFontSize(24);doc.text('Elettrica o Termica',42,23);
    doc.setFont('helvetica','normal');doc.setFontSize(11);doc.setTextColor(205,232,220);doc.text('Report confronto costo reale auto · '+SITE_URL,42,31);
    doc.setFont('helvetica','bold');doc.setTextColor(66,245,147);doc.setFontSize(26);doc.text(saving,42,45);
    doc.setFontSize(10);doc.setTextColor(205,232,220);doc.text('Risparmio stimato nel periodo selezionato',104,44);

    function card(x,y,w,h,title,value,sub,photo,type){
      doc.setFillColor(247,250,248);doc.roundedRect(x,y,w,h,6,6,'F');doc.setDrawColor(223,231,226);doc.roundedRect(x,y,w,h,6,6,'S');
      if(photo){doc.addImage(photo,'JPEG',x+4,y+5,w-8,32)}else{doc.setFillColor(type==='ev'?236:239,type==='ev'?248:244,type==='ev'?242:240);doc.roundedRect(x+4,y+5,w-8,32,5,5,'F')}
      doc.setFont('helvetica','bold');doc.setFontSize(8);doc.setTextColor(type==='ev'?17:95,type==='ev'?184:90,type==='ev'?112:70);doc.text(title,x+5,y+44);
      doc.setFontSize(12);doc.setTextColor(16,24,23);doc.text(String(value),x+5,y+53,{maxWidth:w-10});
      if(sub){doc.setFont('helvetica','normal');doc.setFontSize(8);doc.setTextColor(100,115,110);doc.text(String(sub),x+5,y+62,{maxWidth:w-10})}
    }

    let y=72;
    card(14,y,88,70,'AUTO ELETTRICA',evName,text('#evPer100','')+' / 100 km',evPhoto,'ev');
    card(108,y,88,70,'AUTO TERMICA',iceName,text('#icePer100','')+' / 100 km',icePhoto,'ice');
    y+=82;
    doc.setFillColor(236,248,242);doc.roundedRect(14,y,182,32,6,6,'F');
    doc.setFont('helvetica','bold');doc.setFontSize(11);doc.setTextColor(16,24,23);doc.text('Sintesi del confronto',20,y+10);
    doc.setFont('helvetica','normal');doc.setFontSize(10);doc.setTextColor(65,85,76);
    doc.text('Elettrica €/100 km: '+text('#evPer100','-')+' · Termica €/100 km: '+text('#icePer100','-')+' · Break-even: '+text('#breakEven','-'),20,y+20,{maxWidth:170});
    y+=46;
    doc.setFont('helvetica','bold');doc.setFontSize(12);doc.setTextColor(16,24,23);doc.text('Dettaglio generato dal calcolatore',14,y);y+=8;
    doc.setFont('helvetica','normal');doc.setFontSize(9);doc.setTextColor(65,85,76);
    y=addWrappedText(doc,text('#explainBox','Il confronto usa i dati inseriti nel calcolatore, inclusi carburante, ricarica, manutenzione, bollo e anni di possesso.'),14,y,182,5);
    y+=4;
    doc.setDrawColor(223,231,226);doc.line(14,y,196,y);y+=8;
    doc.setFont('helvetica','bold');doc.setFontSize(11);doc.setTextColor(16,24,23);doc.text('Nota metodologica',14,y);y+=7;
    doc.setFont('helvetica','normal');doc.setFontSize(9);doc.setTextColor(65,85,76);
    y=addWrappedText(doc,'Il report è una stima indicativa. Prezzi di acquisto, valore residuo, assicurazione, manutenzione, bollo, superbollo, tariffe energia e carburanti possono variare. Verifica sempre dati reali e condizioni locali prima di decidere.',14,y,182,5);

    doc.setFillColor(7,17,14);doc.roundedRect(14,268,182,14,5,5,'F');
    doc.setTextColor(245,255,249);doc.setFont('helvetica','bold');doc.setFontSize(9);doc.text('Generato da '+SITE_NAME,20,277);
    doc.setTextColor(66,245,147);doc.text('© '+currentYearLabel(),160,277);
    await saveOrSharePdf(doc,'report-elettricaotermica.pdf');
  }

  function patchPdfButton(){
    const btn=byId('downloadPdf');
    if(!btn) return;
    btn.dataset.eotPdfEnhanced='1';
    btn.onclick=function(ev){if(ev)ev.preventDefault(); enhancedPdf(); return false};
  }

  window.EOT_RESET_COOKIE_CHOICE=function(){try{localStorage.removeItem(STORAGE_KEY)}catch(e){} showBanner()};

  function boot(){
    installSafeMobileInputPolish();
    const choice=readChoice();
    if(!choice) showBanner();
    else if(choice==='accepted' && typeof window.EOT_ENABLE_ANALYTICS==='function') window.EOT_ENABLE_ANALYTICS();
    const reset=byId('resetCookieChoice');
    if(reset) reset.addEventListener('click',window.EOT_RESET_COOKIE_CHOICE);
    installFooter();
    patchPdfButton();
    setTimeout(patchPdfButton,1200);
    setTimeout(patchPdfButton,3000);
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot);
  else boot();
  window.addEventListener('load',function(){installSafeMobileInputPolish();installFooter();patchPdfButton();});
  window.addEventListener('motornet:catalog-ready',function(){patchPdfButton();});
})();
