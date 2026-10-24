const $=id=>document.getElementById(id);let img=null,pieces=[],selected=-1,drag=null,viewScale=1,sourceName='referencia';const canvas=$('overlay'),ctx=canvas.getContext('2d'),cleanCanvas=$('cleanLayer'),cleanCtx=cleanCanvas.getContext('2d',{willReadFrequently:true});let editHistory=[],redoHistory=[],cleanDrag=null;function status(t,k=''){$('status').textContent=t;$('status').className=k}function runsOnStudio(){return location.hostname==='127.0.0.1'||location.hostname==='localhost'}function studioRequiredMessage(){return runsOnStudio()?'No responde el estudio en esta PC. Deja abierta la ventana de INICIAR_GAMEB_STUDIO.bat, conecta ChatGPT en la página principal y vuelve a pulsar el botón.':'Netlify solo muestra esta pantalla y no puede generar los PNG. En tu PC ejecuta INICIAR_GAMEB_STUDIO.bat y abre http://127.0.0.1:8766/desarmador.html con el mismo boceto.'}function isTitlePiece(piece){const label=`${piece?.type||''} ${piece?.name||''}`;return /t[ií]tulo|logo|letrero/i.test(label)}function showProgress(title,percent,detail='',phase=''){const box=$('workProgress');if(!box)return;box.hidden=false;box.classList.toggle('is-waiting',percent===null);if(percent!==null)$('progressBar').style.width=Math.max(0,Math.min(100,percent))+'%';$('progressPercent').textContent=percent===null?'…':Math.round(percent)+'%';$('progressTitle').textContent=title;$('progressDetail').textContent=detail;const ids=['stepLeer','stepUnir','stepRecortar','stepFondo','stepInspeccionar'];const phases={leer:0,unir:1,recortar:2,fondo:3,inspeccionar:4,done:5};for(const [i,id] of ids.entries()){const el=$(id);if(!el)continue;el.classList.toggle('active',phases[phase]===i);el.classList.toggle('done',phase==='done'||(phases[phase]!==undefined&&i<phases[phase]));}}function hideProgressLater(){const box=$('workProgress');if(box){box.classList.remove('is-waiting');$('progressBar').style.width='100%';$('progressPercent').textContent='100%';$('progressTitle').textContent='Proceso finalizado';$('progressDetail').textContent='Puedes cargar otro boceto cuando quieras.';for(const id of ['stepLeer','stepUnir','stepRecortar','stepFondo','stepInspeccionar']){const el=$(id);if(el)el.classList.add('done');}}}function dims(){return {w:img?img.naturalWidth:0,h:img?img.naturalHeight:0}}function resizeCanvas(){if(!img)return;const box=$('source').getBoundingClientRect();viewScale=box.width/img.naturalWidth;for(const cv of [canvas,cleanCanvas]){cv.width=img.naturalWidth;cv.height=img.naturalHeight;cv.style.width=box.width+'px';cv.style.height=(img.naturalHeight*viewScale)+'px'}$('stageInner').style.width=box.width+'px';$('stageInner').style.height=(img.naturalHeight*viewScale)+'px';if(!cleanCanvas.dataset.ready)resetClean(false);draw()}function toImagePoint(e){const r=canvas.getBoundingClientRect();return {x:Math.max(0,Math.min(img.naturalWidth,(e.clientX-r.left)/viewScale)),y:Math.max(0,Math.min(img.naturalHeight,(e.clientY-r.top)/viewScale))}}function draw(){
 if(!img)return;
 ctx.clearRect(0,0,canvas.width,canvas.height);
 const scaleFont=Math.max(10,Math.min(18,canvas.width/110));
 pieces.forEach((p,i)=>{
  ctx.save();
  // Las cajas son guías de selección discretas, no se presentan como siluetas.
  ctx.strokeStyle=i===selected?'rgba(255,209,102,.95)':'rgba(85,186,255,.55)';
  ctx.lineWidth=i===selected?Math.max(2,canvas.width/900):Math.max(1,canvas.width/1800);
  ctx.setLineDash(i===selected?[]:[5,5]);
  ctx.strokeRect(p.x,p.y,p.w,p.h);
  ctx.setLineDash([]);
  // Si ya existe máscara alfa, dibuja el contorno real de sus píxeles opacos.
  if(p.processedCanvas&&p.processedCanvas.width&&p.processedCanvas.height){
   try{
    const mc=p.processedCanvas, mw=mc.width,mh=mc.height, md=mc.getContext('2d',{willReadFrequently:true}).getImageData(0,0,mw,mh).data;
    const step=Math.max(1,Math.floor(Math.max(mw,mh)/900));
    ctx.fillStyle=i===selected?'#ffdf70':'#35f0c0';
    for(let yy=0;yy<mh;yy+=step){for(let xx=0;xx<mw;xx+=step){
      const a=md[(yy*mw+xx)*4+3];if(a<32)continue;
      const left=xx===0?0:md[(yy*mw+Math.max(0,xx-step))*4+3];
      const right=xx+step>=mw?0:md[(yy*mw+Math.min(mw-1,xx+step))*4+3];
      const up=yy===0?0:md[(Math.max(0,yy-step)*mw+xx)*4+3];
      const down=yy+step>=mh?0:md[(Math.min(mh-1,yy+step)*mw+xx)*4+3];
      if(left<32||right<32||up<32||down<32){const rw=Math.max(1,Math.min(step,mw-xx))*p.w/mw,rh=Math.max(1,Math.min(step,mh-yy))*p.h/mh;ctx.fillRect(p.x+xx*p.w/mw,p.y+yy*p.h/mh,rw,rh)}
    }}
   }catch(e){/* Si la máscara no se puede leer, se conserva la caja de selección. */}
  }
  // Etiqueta pequeña, fuera del centro del componente.
  const label=(i+1)+'. '+(p.name||'Componente');ctx.font=`600 ${scaleFont}px sans-serif`;
  const tw=Math.min(ctx.measureText(label).width+8,Math.max(52,p.w));
  const ly=p.y>=scaleFont+6?p.y-scaleFont-6:p.y+2;
  ctx.fillStyle=i===selected?'rgba(255,209,102,.94)':'rgba(8,20,38,.76)';ctx.fillRect(p.x,ly,tw,scaleFont+5);
  ctx.fillStyle=i===selected?'#111827':'#d9edff';ctx.fillText(label,p.x+4,ly+scaleFont);
  ctx.restore();
 });
}
function renderList(){const root=$('pieceList');root.innerHTML='';if(!pieces.length){root.innerHTML='<div class="empty">Todavía no hay recortes.</div>';$('pieceMeta').textContent='Sin pieza seleccionada.';return}pieces.forEach((p,i)=>{const d=document.createElement('div');d.className='piece';const c=document.createElement('canvas');const scale=Math.min(1,180/Math.max(Number(p.w)||1,Number(p.h)||1));c.width=Math.max(1,Math.round((Number(p.w)||1)*scale));c.height=Math.max(1,Math.round((Number(p.h)||1)*scale));const tc=c.getContext('2d');tc.clearRect(0,0,c.width,c.height);try{if(p.processedCanvas&&p.processedCanvas.width&&p.processedCanvas.height){tc.drawImage(p.processedCanvas,0,0,p.processedCanvas.width,p.processedCanvas.height,0,0,c.width,c.height)}else if(img&&img.complete&&img.naturalWidth){const sx=Math.max(0,Math.min(img.naturalWidth-1,Math.floor(Number(p.x)||0))),sy=Math.max(0,Math.min(img.naturalHeight-1,Math.floor(Number(p.y)||0))),sw=Math.max(1,Math.min(img.naturalWidth-sx,Math.round(Number(p.w)||1))),sh=Math.max(1,Math.min(img.naturalHeight-sy,Math.round(Number(p.h)||1)));tc.drawImage(img,sx,sy,sw,sh,0,0,c.width,c.height)}else{throw new Error('La imagen original no está disponible')}}catch(err){tc.fillStyle='#17263b';tc.fillRect(0,0,c.width,c.height);tc.fillStyle='#f4ce76';tc.font='10px sans-serif';tc.textAlign='center';tc.fillText('Sin vista',c.width/2,c.height/2)}const im=new Image();im.alt='Vista previa de '+(p.name||'componente');im.src=c.toDataURL('image/png');const info=document.createElement('div');const title=document.createElement('strong');title.textContent=p.name;const small=document.createElement('small');small.textContent=`${archivoDe(p)}.png · ${p.type} · x${Math.round(p.x)} y${Math.round(p.y)} · ${Math.round(p.w)}×${Math.round(p.h)}${p.processedCanvas?' · fondo procesado':''}`;const approval=document.createElement('small');approval.style.cssText='display:block;margin-top:3px;font-size:10px;color:'+(p.qualityAudit&&p.qualityAudit.passed?'#4cd5a5':p.qualityAudit?'#f4ce76':'#aab9d1');approval.textContent=p.qualityAudit?`Aprobación técnica: ${p.qualityAudit.score}% · ${p.qualityAudit.passed?'pasa controles básicos':'requiere revisión'}`:'Aprobación técnica: pendiente de analizar';const sel=document.createElement('button');sel.textContent='Editar';sel.onclick=()=>selectPiece(i);const inspect=document.createElement('button');inspect.type='button';inspect.textContent='Inspeccionar';inspect.setAttribute('aria-label','Inspeccionar '+(p.name||('Componente '+(i+1))));inspect.addEventListener('click',(ev)=>{ev.preventDefault();ev.stopPropagation();try{openInspect(i);}catch(err){console.error('Error al abrir inspección:',err);status('No se pudo abrir la inspección: '+(err.message||err),'err');}});const del=document.createElement('button');del.textContent='Quitar';del.onclick=()=>{pieces.splice(i,1);selected=-1;draw();renderList()};info.append(title,small,approval,document.createElement('br'),sel,inspect,del);d.append(im,info);root.append(d)});if(selected>=0&&pieces[selected]){$('pieceMeta').textContent=`${archivoDe(pieces[selected])}.png · x=${Math.round(pieces[selected].x)}, y=${Math.round(pieces[selected].y)}, ancho=${Math.round(pieces[selected].w)}, alto=${Math.round(pieces[selected].h)}`}}function selectPiece(i){if(!Number.isInteger(i)||i<0||i>=pieces.length||!pieces[i])return;selected=i;const p=pieces[i];$('pieceName').value=p.name||`Componente ${i+1}`;$('pieceType').value=p.type||'Otro';draw();renderList();if(inspectIndex===i&&$('inspectModal')?.classList.contains('open'))updateInspect()}function addPiece(x,y,w,h,name,type='Otro'){const W=img.naturalWidth,H=img.naturalHeight;x=Math.max(0,Math.min(W-1,x));y=Math.max(0,Math.min(H-1,y));w=Math.max(1,Math.min(W-x,w));h=Math.max(1,Math.min(H-y,h));if(w<3||h<3)return;pieces.push({x,y,w,h,name:name||`Componente ${pieces.length+1}`,type});selected=pieces.length-1;selectPiece(selected)}let inspectIndex=-1,inspectZoom=1;function canvasHasVisiblePixels(canvas){
 if(!canvas||!canvas.width||!canvas.height)return false;
 try{const ctx=canvas.getContext('2d',{willReadFrequently:true});if(!ctx)return false;const d=ctx.getImageData(0,0,canvas.width,canvas.height).data;const step=Math.max(4,Math.floor((canvas.width*canvas.height)/12000)*4);for(let i=3;i<d.length;i+=step){if(d[i]>8)return true;}return false;}catch(_){return false;}
}
function makePiecePreview(i){
 const p=pieces[i];
 if(!p||!img||!img.complete||!img.naturalWidth)throw new Error('La imagen original no está cargada o no hay un recorte seleccionado.');
 if(p.processedCanvas&&p.processedCanvas.width>0&&p.processedCanvas.height>0&&canvasHasVisiblePixels(p.processedCanvas))return p.processedCanvas.toDataURL('image/png');
 const W=img.naturalWidth,H=img.naturalHeight;
 const x=Math.max(0,Math.min(W-1,Math.floor(Number(p.x)||0))),y=Math.max(0,Math.min(H-1,Math.floor(Number(p.y)||0)));
 const w=Math.max(1,Math.min(W-x,Math.round(Number(p.w)||1))),h=Math.max(1,Math.min(H-y,Math.round(Number(p.h)||1)));
 if(w<1||h<1)throw new Error('El recorte tiene dimensiones inválidas.');
 const out=document.createElement('canvas');out.width=w;out.height=h;
 const c=out.getContext('2d');if(!c)throw new Error('No se pudo crear el lienzo de vista previa.');
 const source=(cleanCanvas.dataset.ready==='1'&&cleanCanvas.width===W&&cleanCanvas.height===H)?cleanCanvas:img;
 c.clearRect(0,0,w,h);c.drawImage(source,x,y,w,h,0,0,w,h);
 return out.toDataURL('image/png');
}function cropCanvasFor(i){const p=pieces[i];if(p.processedCanvas)return p.processedCanvas;const out=document.createElement('canvas');out.width=Math.max(1,Math.round(p.w));out.height=Math.max(1,Math.round(p.h));out.getContext('2d',{willReadFrequently:true}).drawImage(cleanCanvas.dataset.ready==='1'?cleanCanvas:img,p.x,p.y,p.w,p.h,0,0,out.width,out.height);return out}
function updateInspect(){
 if(inspectIndex<0||!pieces[inspectIndex])return;
 const index=inspectIndex,p=pieces[index];
 $('inspectCounter').textContent=`Pieza ${index+1} de ${pieces.length}`;
 $('inspectName').value=p.name||`Componente ${index+1}`;
 const allowed=[...$('inspectType').options].map(o=>o.value);
 $('inspectType').value=allowed.includes(p.type)?p.type:'Otro';
 const preview=$('inspectImage'),host=$('inspectPreview');
 $('inspectStatus').textContent='Preparando vista previa…';
 try{
   const processedOK=!!(p.processedCanvas&&p.processedCanvas.width>0&&p.processedCanvas.height>0&&canvasHasVisiblePixels(p.processedCanvas));
   const originalSource=(cleanCanvas.dataset.ready==='1'&&cleanCanvas.width===img.naturalWidth&&cleanCanvas.height===img.naturalHeight)?cleanCanvas:img;
   const source=processedOK?p.processedCanvas:originalSource;
   const sx=processedOK?0:Math.max(0,Math.floor(Number(p.x)||0));
   const sy=processedOK?0:Math.max(0,Math.floor(Number(p.y)||0));
   const sw=processedOK?source.width:Math.max(1,Math.min(source.width-sx,Math.round(Number(p.w)||1)));
   const sh=processedOK?source.height:Math.max(1,Math.min(source.height-sy,Math.round(Number(p.h)||1)));
   if(!source||!source.width||!source.height||!sw||!sh)throw new Error('La pieza no tiene una imagen válida. Comprueba que la imagen original siga cargada.');
   preview.width=sw;preview.height=sh;
   const pc=preview.getContext('2d');if(!pc)throw new Error('No se pudo crear el visor.');
   pc.clearRect(0,0,sw,sh);pc.imageSmoothingEnabled=true;pc.imageSmoothingQuality='high';
   pc.drawImage(source,sx,sy,sw,sh,0,0,sw,sh);
   const hostW=host.clientWidth||640,hostH=host.clientHeight||420;
   const fit=Math.min(Math.max(100,hostW-24)/sw,Math.max(100,hostH-24)/sh,1);
   const scale=Math.max(.1,fit*Math.max(.4,Math.min(3,inspectZoom)));
   preview.style.width=Math.max(1,Math.round(sw*scale))+'px';
   preview.style.height=Math.max(1,Math.round(sh*scale))+'px';preview.style.transform='none';
   $('inspectStatus').textContent=processedOK?'Pieza procesada. Revisa los bordes antes de aprobar.':(p.processedCanvas?'La máscara procesada estaba vacía; se muestra el recorte original para no ocultar la pieza.':'Recorte original cargado. Todavía no se ha separado el fondo.');
 }catch(err){
   preview.width=1;preview.height=1;preview.style.width='1px';preview.style.height='1px';
   $('inspectStatus').textContent='No se pudo mostrar el recorte: '+err.message;
 }
 $('inspectDimensions').textContent=`Recorte: ${Math.round(p.w)} × ${Math.round(p.h)} px · Posición original: x=${Math.round(p.x)}, y=${Math.round(p.y)}${p.processedCanvas?' · máscara procesada':''}`;
 $('inspectPrev').disabled=index<=0;$('inspectNext').disabled=index>=pieces.length-1;$('inspectRemoveBg').disabled=isBackgroundPiece(p);$('inspectRemoveBg').title=isBackgroundPiece(p)?'No aplicar segmentación de primer plano a una escena de fondo':'Quitar el fondo del objeto seleccionado';$('inspectRemoveBg').textContent=isBackgroundPiece(p)?'Fondo base: conservar escena':'Quitar fondo de esta pieza';
 $('inspectAIResult').textContent=p.aiReview||'Todavía no se ha analizado este recorte.';
 updateQualityReport();
}
function openInspect(i){
 const index=Number(i);
 if(!Number.isInteger(index)||index<0||index>=pieces.length||!pieces[index]){status('No hay un recorte válido para inspeccionar. Ejecuta primero la identificación de componentes.','err');return false;}
 if(!img||!img.complete||!img.naturalWidth){status('La imagen original no está cargada. Vuelve a cargar el boceto.','err');return false;}
 inspectIndex=index;selected=index;inspectZoom=1;
 const modal=$('inspectModal'),host=$('inspectPreview'),preview=$('inspectImage');
 if(!modal||!host||!preview){status('Falta un elemento de la ventana de inspección. Recarga el módulo Desarmador.','err');return false;}
 modal.classList.add('open');modal.style.display='flex';host.className='inspectPreview preview-checker';
 preview.width=1;preview.height=1;preview.style.width='1px';preview.style.height='1px';
 $('inspectStatus').textContent='Preparando vista previa del recorte…';
 try{updateInspect();draw();renderList();return true;}catch(err){console.error('Error en vista de inspección:',err);$('inspectStatus').textContent='No se pudo cargar la pieza: '+(err.message||err);return false;}
}
function alphaStats(c){const d=c.getContext('2d',{willReadFrequently:true}).getImageData(0,0,c.width,c.height).data;let transparent=0,semi=0;for(let i=3;i<d.length;i+=4){if(d[i]===0)transparent++;else if(d[i]<255)semi++}return {transparent,semi,total:c.width*c.height,pct:Math.round(transparent/(c.width*c.height)*100)}}
function qualityAudit(c){const d=c.getContext('2d',{willReadFrequently:true}).getImageData(0,0,c.width,c.height).data,W=c.width,H=c.height,total=W*H;let transparent=0,semi=0,opaque=0,strong=0,edge=0,edgeOpaque=0,edgeSemi=0;for(let y=0;y<H;y++){for(let x=0;x<W;x++){const a=d[(y*W+x)*4+3];if(a===0)transparent++;else if(a<255)semi++;else opaque++;if(a>=128)strong++;if(x===0||y===0||x===W-1||y===H-1){edge++;if(a===255)edgeOpaque++;else if(a>0)edgeSemi++}}}const alphaPct=transparent/total*100,semiPct=semi/total*100,edgeSolidPct=edge?edgeOpaque/edge*100:0;let score=100;if(alphaPct<1)score-=55;else if(alphaPct<8)score-=25;if(semiPct<0.05)score-=8;if(edgeSolidPct>45)score-=25;else if(edgeSolidPct>20)score-=12;if(W<64||H<64)score-=10;const strongPct=strong/total*100;if(strongPct<10)score-=55;score=Math.max(0,Math.min(89,Math.round(score)));const flags=['Índice técnico de señales de riesgo; NO mide la exactitud semántica ni garantiza que el objeto esté completo. La aprobación visual siempre queda pendiente.'];if(strongPct<10)flags.push('El dibujo casi desapareció: la máscara dejó el recorte vacío o en una mancha.');if(alphaPct<1)flags.push('No se detecta transparencia suficiente; quizá el fondo sigue intacto.');if(edgeSolidPct>20)flags.push('Muchos píxeles opacos tocan el borde: revisa si el objeto quedó cortado o si falta retirar fondo.');if(semiPct<0.05)flags.push('Hay muy pocos píxeles semitransparentes; revisa posibles bordes duros o halos.');if(W<128||H<128)flags.push('Resolución pequeña para un recurso de alta calidad.');flags.push('Compara la pieza con la imagen original: revisa adornos, puntas, letras cortadas y elementos vecinos. La máscara puede eliminar detalles aunque tenga transparencia.');return {score,alphaPct:Math.round(alphaPct*10)/10,semiPct:Math.round(semiPct*10)/10,edgeSolidPct:Math.round(edgeSolidPct),width:W,height:H,flags,passed:false}}
function updateQualityReport(){const out=$('qualityReport');if(!out)return;const p=pieces[inspectIndex];if(!p){out.textContent='Selecciona una pieza.';return}if(!p.processedCanvas){out.innerHTML='<strong>Sin evaluación todavía.</strong><br>Se necesita una máscara procesada para medir la transparencia real. La detección del objeto por sí sola no valida el recorte.';return}const q=qualityAudit(p.processedCanvas);const label='Revisión visual necesaria';out.innerHTML=`<div style="font-size:18px;font-weight:800;color:${q.passed?'#4cd5a5':'#f4ce76'}">Índice técnico: ${q.score}/100 · ${label}</div><p>Dimensiones: ${q.width}×${q.height}px · Transparencia alfa: ${q.alphaPct}% · Bordes semitransparentes: ${q.semiPct}% · Borde exterior opaco: ${q.edgeSolidPct}%</p><ul>${q.flags.map(f=>`<li>${f}</li>`).join('')}</ul><p><strong>Nota:</strong> no es un porcentaje estadístico de precisión. No detecta por sí solo si se borraron partes del objeto; confirma visualmente sobre fondos claro, oscuro y a cuadros.</p>`;p.qualityAudit=q;$('inspectRegister').title=q.passed?'Pasa controles técnicos básicos; inspección visual aún requerida':'Revisa el contorno antes de dar de alta';renderList()}
async function removeBgFromSelectedPiece(){if(inspectIndex<0||!pieces[inspectIndex])return;const p=pieces[inspectIndex],button=$('inspectRemoveBg');if(isBackgroundPiece(p)){ $('inspectStatus').textContent='Esta pieza está clasificada como Fondo base / escena. No se aplica quitar-fondo de primer plano porque podría borrar el escenario. Para limpiar objetos superpuestos, usa la limpieza manual y revisa la reconstrucción por separado.';return;}button.disabled=true;button.textContent='Separando silueta…';$('inspectStatus').textContent='Procesando únicamente esta pieza con segmentación de primer plano. El original permanece intacto.';try{const sourceData=makePiecePreview(inspectIndex);const r=await fetch('/api/remove-background',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({image:sourceData,inner:innerBoxFor(p),kind:[p.type||'',p.fileName||''].filter(Boolean).join(' ')},laminaPayload(p,!(p.processedCanvas&&canvasHasVisiblePixels(p.processedCanvas)))))});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'No se pudo separar el fondo');p.processedDataURL=d.image;const matteImage=new Image();matteImage.onload=()=>{const pc=document.createElement('canvas');pc.width=matteImage.naturalWidth;pc.height=matteImage.naturalHeight;pc.getContext('2d',{willReadFrequently:true}).drawImage(matteImage,0,0);p.processedCanvas=pc;applyTrim(p,d);updateInspect();updateQualityReport();renderList();$('inspectStatus').textContent=`Segmentación terminada. Transparencia real: ${alphaStats(pc).pct}%. Se calculó un índice técnico de control; no es una garantía de precisión. Revisa contorno y detalles.`};matteImage.src=d.image;$('cleanStatus').textContent='Se generó una versión transparente de esta pieza. El original no se modificó.'}catch(e){$('inspectStatus').textContent='No se pudo separar el fondo: '+e.message+' Instala las dependencias de segmentación y vuelve a intentarlo. No se aplicaron cambios.'}finally{button.disabled=false;button.textContent='Quitar fondo de esta pieza'}}$('previewChecker').onclick=()=>{$('inspectPreview').className='inspectPreview preview-checker'};$('previewDark').onclick=()=>{$('inspectPreview').className='inspectPreview preview-dark'};$('previewLight').onclick=()=>{$('inspectPreview').className='inspectPreview preview-light'};$('inspectRemoveBg').onclick=removeBgFromSelectedPiece;$('qualityRefresh').onclick=updateQualityReport;
function closeInspect(){const m=$('inspectModal');if(m){m.classList.remove('open');m.style.display='none';}}$('closeInspect').onclick=closeInspect;$('inspectModal').addEventListener('click',e=>{if(e.target===$('inspectModal'))closeInspect()});$('inspectPrev').onclick=()=>{if(inspectIndex>0){inspectIndex--;inspectZoom=1;updateInspect();updateQualityReport()}};$('inspectNext').onclick=()=>{if(inspectIndex<pieces.length-1){inspectIndex++;inspectZoom=1;updateInspect();updateQualityReport()}};$('inspectZoomIn').onclick=()=>{inspectZoom=Math.min(3,inspectZoom+.2);updateInspect()};$('inspectZoomOut').onclick=()=>{inspectZoom=Math.max(.4,inspectZoom-.2);updateInspect()};$('inspectApply').onclick=()=>{if(inspectIndex<0)return;pieces[inspectIndex].name=$('inspectName').value.trim()||`Componente ${inspectIndex+1}`;pieces[inspectIndex].type=$('inspectType').value;selectPiece(inspectIndex);$('inspectStatus').textContent='Cambios aplicados al recorte. Todavía no se ha dado de alta.';updateInspect();renderList()};$('inspectRegister').onclick=async()=>{if(inspectIndex<0)return;pieces[inspectIndex].name=$('inspectName').value.trim()||`Componente ${inspectIndex+1}`;pieces[inspectIndex].type=$('inspectType').value;try{$('inspectRegister').disabled=true;const j=await savePiece(inspectIndex);$('inspectStatus').textContent=`✓ Dada de alta en Biblioteca visual: ${j.name} (${Math.round(pieces[inspectIndex].w)}×${Math.round(pieces[inspectIndex].h)} px).`;status(`Pieza dada de alta: ${j.name}.`,'ok');renderList()}catch(e){$('inspectStatus').textContent='Error al dar de alta: '+e.message;status('Error al guardar: '+e.message,'err')}finally{$('inspectRegister').disabled=false}};
function formatTitleReview(d){const issues=(Array.isArray(d.issues)?d.issues:[]).slice(0,6).map(i=>`${i.severity||'Nota'}: ${i.title||''}. ${i.detail||''}`.trim());return [`${d.quality||'Revisar'}. ${d.summary||''}`.trim(),...issues].filter(Boolean).join('\n')}
async function inspectTitleWithAI(){if(inspectIndex<0||!pieces[inspectIndex]||!img)return;const p=pieces[inspectIndex],button=$('inspectAIButton');button.disabled=true;$('inspectAIResult').textContent='Comparando este recorte con el boceto completo…';try{const crop=makePiecePreview(inspectIndex);const full=document.createElement('canvas');const scale=Math.min(1,1400/Math.max(img.naturalWidth,img.naturalHeight));full.width=Math.max(1,Math.round(img.naturalWidth*scale));full.height=Math.max(1,Math.round(img.naturalHeight*scale));full.getContext('2d').drawImage(img,0,0,full.width,full.height);const r=await fetch('/api/inspect-crop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:crop,original:full.toDataURL('image/png'),name:$('inspectName').value||p.name,category:$('inspectType').value||p.type,words:p.titleWords||[],notes:$('inspectAINotes').value})});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'No se pudo inspeccionar');p.aiReview=formatTitleReview(d);const alta=(Array.isArray(d.issues)?d.issues:[]).some(issue=>issue&&issue.severity==='Alta');if(isTitlePiece(p)&&(!d.ready_to_register||alta)){p.skipSave=true;p.titleFailed=true;p.titleReason=p.aiReview}$('inspectAIResult').textContent=p.aiReview}catch(e){$('inspectAIResult').textContent=e.message}finally{button.disabled=false}}
$('inspectAIButton').onclick=inspectTitleWithAI;
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeInspect();if($('inspectModal').classList.contains('open')&&e.key==='ArrowLeft')$('inspectPrev').click();if($('inspectModal').classList.contains('open')&&e.key==='ArrowRight')$('inspectNext').click()});
$('file').onchange=()=>{const f=$('file').files[0];if(!f)return;if(!/^image\/(png|jpeg|webp)$/.test(f.type)){status('Formato no admitido.','err');return}const url=URL.createObjectURL(f);img=new Image();img.onload=()=>{$('source').src=url;$('source').hidden=false;$('stageEmpty').hidden=true;sourceName=f.name.replace(/\.[^.]+$/,'');pieces=[];selected=-1;cleanCanvas.dataset.ready='';editHistory=[];redoHistory=[];resizeCanvas();resetClean(false);renderList();status(`Imagen cargada: ${img.naturalWidth}×${img.naturalHeight}px.`, 'ok');$('cleanStatus').textContent='Copia editable creada. El original permanece intacto.'};img.onerror=()=>status('No se pudo abrir la imagen.','err');img.src=url};window.addEventListener('resize',()=>{if(img)resizeCanvas()});// ===== IDENTIFICACIÓN DE COMPONENTES =====
function innerBoxFor(piece){const box=piece&&piece.initialBox;if(!box)return {x:0,y:0,w:Math.max(1,Math.round(piece?.w||1)),h:Math.max(1,Math.round(piece?.h||1))};return {x:Math.max(0,Math.round(box.x-piece.x)),y:Math.max(0,Math.round(box.y-piece.y)),w:Math.max(1,Math.round(box.w)),h:Math.max(1,Math.round(box.h))}}
function laminaPayload(piece, usingOriginal){
 if(!usingOriginal||!piece)return {};
 const rel=box=>({x:Math.round(Number(box.x)-Number(piece.x)),y:Math.round(Number(box.y)-Number(piece.y)),w:Math.round(Number(box.w)),h:Math.round(Number(box.h))});
 const payload={};
 if(piece.hole&&[piece.hole.x,piece.hole.y,piece.hole.w,piece.hole.h].every(n=>Number.isFinite(Number(n))))payload.hole=rel(piece.hole);
 if(Array.isArray(piece.erase)&&piece.erase.length)payload.erase=piece.erase.filter(box=>box&&[box.x,box.y,box.w,box.h].every(n=>Number.isFinite(Number(n)))).map(rel);
 return payload;
}
function archivoDe(p){
 const given=String(p&&p.fileName||'').toLowerCase().replace(/[^a-z0-9_]+/g,'_').replace(/^_+|_+$/g,'');
 if(given)return given.slice(0,70);
 const slug=String(p&&p.name||'componente').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_+|_+$/g,'');
 return (slug||'componente').slice(0,70);
}
function applyTrim(piece,meta){if(!piece||!meta||!Number.isFinite(meta.trimX)||!Number.isFinite(meta.trimY)||!piece.processedCanvas)return;piece.x+=meta.trimX;piece.y+=meta.trimY;piece.w=piece.processedCanvas.width;piece.h=piece.processedCanvas.height}
function isBackgroundPiece(piece){
 const value=String(piece?.type||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
 const name=String(piece?.name||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
 return value.includes('fondo') || name.includes('fondo base') || name.includes('escena de fondo');
}
$('detectionMode').onchange=()=>{
 const background=$('detectionMode').value==='background';
 $('backgroundModeHint').textContent=background
  ?'Modo Fondo base / escena: detecta la escena ambiental. No quita objetos superpuestos ni reconstruye automáticamente lo que está oculto. Revisa el resultado y limpia o reconstruye esas zonas por separado.'
  :'El Fondo es la escena ambiental detrás de las capas. Los elementos visibles superpuestos deben guardarse como piezas separadas.';
 $('aiInstructions').placeholder=background
  ?'Ej. localiza la escena ambiental detrás del título y los jackpots; no inventes las zonas ocultas'
  :'Ej. separa los números de los jackpots o revisa el borde del título';
};
$('analyzeAI').onclick=async()=>{
 if(!img||!img.naturalWidth)return status('Primero carga una imagen válida.','err');
 const btn=$('analyzeAI'),backgroundMode=$('detectionMode').value==='background';
 btn.disabled=true;btn.textContent='Analizando imagen con IA…';showProgress('Leyendo palabras y piezas',5,'Preparando el boceto original.','leer');
 status(backgroundMode?'Buscando la escena de fondo. La IA no puede recuperar píxeles que estén tapados en la captura.':'Analizando componentes visibles de la imagen.','');
 try{
  const tmp=document.createElement('canvas');tmp.width=img.naturalWidth;tmp.height=img.naturalHeight;
  const tctx=tmp.getContext('2d');if(!tctx)throw Error('No se pudo preparar la imagen para el análisis.');
  tctx.drawImage(img,0,0);const image=tmp.toDataURL('image/png');
  const common=backgroundMode
   ?'MODO EXCLUSIVO FONDO BASE / ESCENA. Busca únicamente la escena completa que está detrás de las capas. NO clasifiques como fondo el título/logotipo, jackpots, cantidades, marco de rodillos, símbolos, piezas independientes, botones, contadores, textos ni paneles. Devuelve una sola región, con nombre exacto "Fondo base / escena" y tipo "Fondo". No la partas en pedazos. No devuelvas símbolos ni controles en este modo. No inventes píxeles ocultos ni afirmes que se han reconstruido. Si la escena completa está cubierta, indícalo en el resumen y devuelve esa única región, la más grande. '
   :'MODO TODOS LOS COMPONENTES. Devuelve solo la lámina: un fondo_principal con la escena completa, un título o logo, el marco de rodillos si hay rodillos, un símbolo por cada icono dentro de los rodillos, cada jackpot, cada botón, cada panel y los letreros de líneas. No partas el paisaje en piezas. Un bonus dentro de un rodillo es un símbolo. REGLA DE FORMA, para cualquier boceto: no busques un dibujo concreto. En cada símbolo mira solo el contorno exterior. Si ese contorno es un cuadrado, la caja es el cuadrado completo, con su marco y todo lo pintado adentro. Si el contorno no es un cuadrado, la caja sigue ese contorno hasta el último borde. El color del filo es el del propio símbolo y lo de afuera queda transparente. REGLA CRÍTICA PARA TÍTULOS/LOGOS: el título puede ser cualquier imagen, no un juego fijo. Si tiene letras, la caja abarca el letrero completo y sus adornos. Si es un dibujo sin palabras, no inventes palabras: una parte role imagen cubre el logo entero. Analiza primero el componente entero y luego fija su caja exterior. Usa una región de búsqueda generosa para que la segmentación tenga margen; no cortes los adornos para evitar objetos cercanos. Mantén los jackpots vecinos como componentes separados aunque las cajas se toquen o se solapen un poco. El Fondo es exclusivamente la escena ambiental detrás de las capas superpuestas; nunca incluyas en el fondo títulos, logos, jackpots, cifras, marcos, símbolos, personajes independientes, botones, indicadores ni textos. No inventes elementos ocultos. Evita cajas gigantes que mezclen componentes diferentes y evita duplicados casi idénticos. Devuelve coordenadas en píxeles de la imagen original. Prioriza precisión sobre cantidad. ';
  const userNotes='Automatización total: este boceto puede ser cualquier juego. Identifica solo lo que se ve. Para un título con palabras, lista cada palabra y cada adorno. Si el título es un dibujo sin letras, una parte role imagen cubre el logo. Si no puedes encerrar una palabra que sí se lee, márcala como faltante. El fondo es la escena completa, id fondo_principal. El marco, si hay rodillos, lleva hole con la ventana interior. En placas y paneles el monto va en parts con role cifra y no es un PNG. Un símbolo y un botón por archivo, con el nombre que se ve. No ancles el símbolo a un dibujo conocido. Si su contorno exterior es un cuadrado, incluye el cuadrado entero; si no lo es, sigue ese contorno completo. No devuelvas decoración, efectos ni pedazos del paisaje.';
  const notes=common+' '+userNotes;
  showProgress('Leyendo el boceto',null,'La IA lista las piezas y, en el título, cada palabra y cada adorno por separado.','leer');const r=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image,name:sourceName,columns:+$('gridCols').value||5,rows:+$('gridRows').value||3,notes})});
  const raw=await r.text();let j;try{j=JSON.parse(raw)}catch(_){throw Error(studioRequiredMessage())}
  if(!r.ok)throw Error(j.error||studioRequiredMessage());
  if(!j.aiUsed)throw Error(j.summary||'No se realizó análisis con IA.');
  const found=Array.isArray(j.components)?j.components:[];
  if(!found.length)throw Error('La IA no encontró regiones claras. Prueba con una imagen más nítida o añade instrucciones.');
  const W=img.naturalWidth,H=img.naturalHeight;
  let candidates=found.map((c,i)=>{
   let x=Number(c.x),y=Number(c.y),w=Number(c.w),h=Number(c.h);
   if(![x,y,w,h].every(Number.isFinite)||w<3||h<3)return null;
   x=Math.max(0,Math.min(W-1,x));y=Math.max(0,Math.min(H-1,y));
   w=Math.max(1,Math.min(W-x,w));h=Math.max(1,Math.min(H-y,h));
   const hole=c.hole&&[c.hole.x,c.hole.y,c.hole.w,c.hole.h].every(n=>Number.isFinite(Number(n)))?{x:Number(c.hole.x),y:Number(c.hole.y),w:Number(c.hole.w),h:Number(c.hole.h)}:null;
   const erase=Array.isArray(c.erase)?c.erase.filter(b=>b&&[b.x,b.y,b.w,b.h].every(n=>Number.isFinite(Number(n)))).map(b=>({x:Number(b.x),y:Number(b.y),w:Number(b.w),h:Number(b.h)})):[];
   return {x,y,w,h,name:String(c.name||`Componente ${i+1}`),type:String(c.type||'Otro'),confidence:Number(c.confidence)||0,id:c.id||'',fileName:String(c.fileName||''),hole,erase,holeEstimated:!!c.holeEstimated,titleFailed:!!c.titleFailed,titleWords:Array.isArray(c.titleWords)?c.titleWords:[],titleOrnaments:Array.isArray(c.titleOrnaments)?c.titleOrnaments:[],titleReason:String(c.titleReason||''),skipSave:!!c.skipSave||!!c.titleFailed};
  }).filter(Boolean);
  if(backgroundMode){
   candidates=candidates.filter(c=>isBackgroundPiece(c)||/escena|paisaje|fondo/i.test(c.name));
   if(!candidates.length)throw Error('La IA no devolvió una región clasificada como fondo. No voy a convertir componentes al azar en fondo; prueba con instrucciones más precisas o crea recortes manuales de las zonas ambientales.');
   candidates=candidates.map(c=>({...c,name:'Fondo base / escena',type:'Fondo',fileName:'fondo_principal',requiresBackgroundReview:true}));
  }
  // Corrección de caja: la caja propuesta por la IA es una estimación inicial, no el límite final.
  // Amplía el área de análisis especialmente en títulos/logos ornamentados, sin fusionar componentes.
  candidates=candidates.map(p=>{
   const label=`${p.type||""} ${p.name||""}`;
   const isTitle=/t[ií]tulo|logo|letrero/i.test(label);
   const isJackpot=/jackpot|grand|major|minor|mini/i.test(label);
   const isSymbol=/s[ií]mbolo/i.test(label);
   const isFrame=/marco/i.test(label);
   const fx=isBackgroundPiece(p)?0:(isTitle?0.32:(isJackpot?0.18:(isSymbol?0.16:(isFrame?0.12:0.12))));
   const fy=isBackgroundPiece(p)?0:(isTitle?0.40:(isJackpot?0.22:(isSymbol?0.18:(isFrame?0.12:0.14))));
   const padX=isBackgroundPiece(p)?0:Math.max(8,Math.round(p.w*fx)),padY=isBackgroundPiece(p)?0:Math.max(8,Math.round(p.h*fy));
   const x=Math.max(0,Math.floor(p.x-padX)),y=Math.max(0,Math.floor(p.y-padY));
   const right=Math.min(W,Math.ceil(p.x+p.w+padX)),bottom=Math.min(H,Math.ceil(p.y+p.h+padY));
   return {...p,x,y,w:Math.max(1,right-x),h:Math.max(1,bottom-y),initialBox:{x:p.x,y:p.y,w:p.w,h:p.h},expandedForValidation:true};
  });
  // Orden de trabajo por capas: objetos de primer plano primero y fondo al final.
  // No se fusionan cajas por tocarse o solaparse: cada componente se procesa por separado.
  const layerRank=p=>isBackgroundPiece(p)?2:(/símbolo|jackpot|bot[oó]n|contador|t[ií]tulo|logo|bonus|decoraci[oó]n|efecto/i.test(`${p.type} ${p.name}`)?0:1);
  candidates.sort((a,b)=>layerRank(a)-layerRank(b));
  // Deduplicación conservadora: elimina solo cajas prácticamente idénticas.
  const kept=[];
  for(const p of candidates){
   const area=p.w*p.h;let duplicate=false;
   for(const q of kept){
    const ix=Math.max(0,Math.min(p.x+p.w,q.x+q.w)-Math.max(p.x,q.x));
    const iy=Math.max(0,Math.min(p.y+p.h,q.y+q.h)-Math.max(p.y,q.y));
    const inter=ix*iy,union=area+q.w*q.h-inter,iou=union?inter/union:0;
    if(iou>.93&&Math.abs(area-q.w*q.h)/Math.max(area,q.w*q.h)<.08){duplicate=true;break;}
   }
   if(!duplicate)kept.push(p);
  }
  if(!kept.length)throw Error('No quedaron recortes válidos después de revisar las coordenadas.');
  // La segmentación se ejecuta de forma secuencial en este orden; el fondo permanece al final.
  pieces=kept;selected=0;selectPiece(0);const titulos=pieces.filter(isTitlePiece);for(const p of titulos){if(p.titleReason)p.aiReview=p.titleReason}showProgress('Uniendo el título',32,titulos.length?titulos.map(p=>p.titleReason||p.name).join(' '):`${pieces.length} componente(s). No había un letrero que unir.`,'unir');
  if(backgroundMode){
   status(`La IA propuso ${pieces.length} región(es) de escena. No se aplicó rembg al fondo para evitar borrar la escena completa. Revisa cada recorte; las partes ocultas por títulos o jackpots no se reconstruyen automáticamente. ${j.summary||''}`,'ok');
  }else{
   status(`Se leyeron ${pieces.length} piezas. El estudio las genera igual al boceto, en tu PC. ChatGPT no dibuja los PNG. ${j.summary||''}`,'ok');
   await processDetectedSilhouettes();
   showProgress('Reconstruyendo el fondo',70,'Se retiran del escenario las piezas ya separadas.','fondo');
   await cleanBackgroundPlate();
   await inspeccionarTitulos();
   showProgress('Guardando PNG',88,'El título incompleto no entra a la biblioteca.','inspeccionar');await saveAllAutomatically();
  }
 }catch(e){let msg=e&&e.message?e.message:String(e);if(/failed to fetch|networkerror|load failed/i.test(msg))msg=studioRequiredMessage();status(msg,'err');showProgress('El proceso se detuvo',null,msg,'leer')}
 finally{btn.disabled=false;btn.textContent='✦ Desarmar con IA y generar PNG'}
};
async function cleanBackgroundPlate(){
 if(!img)return;
 const mask=document.createElement('canvas');mask.width=img.naturalWidth;mask.height=img.naturalHeight;
 const mctx=mask.getContext('2d');let used=0;
 for(const p of pieces){
  if(isBackgroundPiece(p)||!p.processedCanvas||!canvasHasVisiblePixels(p.processedCanvas))continue;
  mctx.drawImage(p.processedCanvas,p.x,p.y,p.w,p.h);used++;
 }
 if(!used)return;
 const src=document.createElement('canvas');src.width=img.naturalWidth;src.height=img.naturalHeight;src.getContext('2d').drawImage(img,0,0);
 try{
  const r=await fetch('/api/clean-background',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:src.toDataURL('image/png'),mask:mask.toDataURL('image/png')})});
  const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'No se pudo limpiar el fondo');
  const im=new Image();await new Promise((resolve,reject)=>{im.onload=resolve;im.onerror=()=>reject(Error('PNG de fondo inválido'));im.src=d.image});
  const pc=document.createElement('canvas');pc.width=im.naturalWidth;pc.height=im.naturalHeight;pc.getContext('2d').drawImage(im,0,0);
  const existing=pieces.filter(isBackgroundPiece);
  const piece=existing[0]||{name:'Fondo base / escena',type:'Fondo'};
  if(!existing.length)pieces.push(piece);
  for(const extra of existing.slice(1))extra.skipSave=true;
  piece.processedCanvas=pc;piece.processedDataURL=d.image;piece.silhouetteReady=true;
  piece.x=0;piece.y=0;piece.w=pc.width;piece.h=pc.height;piece.name='Fondo base / escena';piece.type='Fondo';piece.fileName='fondo_principal';piece.requiresBackgroundReview=true;
 }catch(e){status('El fondo se guardará como recorte original porque no se pudo reconstruir la escena: '+e.message,'err')}
}
// Guardado automático: solo registra PNG válidos. Las piezas de primer plano cuya segmentación falló se omiten, para no presentar un recorte opaco como silueta terminada.
async function inspeccionarTitulos(){
 showProgress('Inspeccionando títulos',78,'Se compara cada letrero con el boceto. Si falta una palabra, esa pieza no entra a la biblioteca.','inspeccionar');
 const full=document.createElement('canvas');
 const scale=Math.min(1,1400/Math.max(img.naturalWidth,img.naturalHeight));
 full.width=Math.max(1,Math.round(img.naturalWidth*scale));
 full.height=Math.max(1,Math.round(img.naturalHeight*scale));
 full.getContext('2d').drawImage(img,0,0,full.width,full.height);
 const original=full.toDataURL('image/png');
 for(let i=0;i<pieces.length;i++){
  const p=pieces[i];
  if(!isTitlePiece(p)||isBackgroundPiece(p))continue;
  if(p.titleFailed){p.skipSave=true;if(p.titleReason)p.aiReview=p.titleReason;continue;}
  try{
   const crop=makePiecePreview(i);
   const words=Array.isArray(p.titleWords)?p.titleWords:[];
   const r=await fetch('/api/inspect-crop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:crop,original,name:p.name,category:p.type,words,notes:words.length?`El letrero debe mostrar estas palabras: ${words.join(', ')}. Si falta alguna, es un defecto de severidad Alta.`:'Este título es una imagen y puede no tener palabras. Compáralo con el boceto: debe estar el logo completo. Si falta una parte visible del mismo letrero, es un defecto de severidad Alta.'})});
   const d=await r.json();
   if(!r.ok||!d.ok)throw Error(d.error||'No se pudo inspeccionar el título');
   p.aiReview=formatTitleReview(d);
   const alta=(Array.isArray(d.issues)?d.issues:[]).some(issue=>issue&&issue.severity==='Alta');
   if(!d.ready_to_register||alta){p.skipSave=true;p.titleFailed=true;p.titleReason=p.aiReview;}
  }catch(e){p.skipSave=true;p.titleFailed=true;p.titleReason='No se pudo comprobar el título contra el boceto: '+e.message;p.aiReview=p.titleReason;}
 }
}
async function saveAllAutomatically(){
 const btn=$('analyzeAI');let saved=0,skipped=[];
 for(let i=0;i<pieces.length;i++){
  const p=pieces[i];
  if(p.skipSave){skipped.push(p.titleReason?`${p.name}: ${p.titleReason}`:p.name);continue;}
  if(!isBackgroundPiece(p)&&!(p.silhouetteReady&&p.processedCanvas&&canvasHasVisiblePixels(p.processedCanvas))){skipped.push(p.name);continue;}
  try{await savePiece(i);saved++;showProgress('Guardando PNG',82+(i+1)/Math.max(1,pieces.length)*18,`Guardando ${saved}/${pieces.length}: ${p.name}`,'inspeccionar');status(`Generando PNG automáticamente: ${saved}/${pieces.length}…`)}catch(e){skipped.push(`${p.name} (${e.message})`)}
 }
 renderList();
 if(skipped.length){status(`Proceso terminado. ${saved} PNG guardados en Biblioteca visual. ${skipped.length} pieza(s) se omitieron porque la segmentación o el guardado falló: ${skipped.slice(0,5).join(' · ')}.`, 'err');showProgress('Proceso terminado con avisos',100,`${saved} PNG guardados; ${skipped.length} pieza(s) omitidas por errores.`,'done')}
 else {status(`Proceso completo: ${saved} PNG guardados en Biblioteca visual. El fondo queda como escena, el marco con el centro vacío y las placas sin la cifra. Revisa el fondo: donde estaban las piezas el relleno es aproximado.`, 'ok');hideProgressLater()}
}
// ===== SEGMENTACIÓN DE PRIMER PLANO =====
async function processDetectedSilhouettes(){
 if(!img)return status('Primero carga el PNG original.','err');
 if(!pieces.length)return status('Primero identifica o crea los recortes.','err');
 const btn=$('analyzeAI');btn.textContent='Generando piezas…';let ok=0,skipped=0,failed=[];
 try{
  for(let i=0;i<pieces.length;i++){
   const piece=pieces[i];
   if(isBackgroundPiece(piece)){
    piece.processedCanvas=null;piece.processedDataURL=null;piece.silhouetteReady=false;piece.requiresBackgroundReview=true;skipped++;
    status(`Pieza ${i+1}/${pieces.length}: ${piece.name}. Es la escena completa; se deja entera.`);
    continue;
   }
   if(piece.processedCanvas&&piece.silhouetteReady&&canvasHasVisiblePixels(piece.processedCanvas)){ok++;continue;}
   btn.textContent=`Generando piezas ${i+1}/${pieces.length}…`;showProgress(`Generando pieza ${i+1}/${pieces.length}`,35+(i/pieces.length)*40,`Generando ${piece.name} igual al boceto. ChatGPT no dibuja esta pieza.`,'recortar');
   status(`Generando ${i+1}/${pieces.length}: ${piece.name}. Sale igual al boceto, sin pedirle el dibujo a ChatGPT.`);
   try{
    const image=makePiecePreview(i),controller=new AbortController(),timer=setTimeout(()=>controller.abort(),180000);
    let r;try{r=await fetch('/api/generate-piece',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({image,inner:innerBoxFor(piece),kind:[piece.type||'',piece.fileName||''].filter(Boolean).join(' ')},laminaPayload(piece,true))),signal:controller.signal})}finally{clearTimeout(timer)}
    let d;try{d=await r.json()}catch(_){throw Error(`Respuesta inválida del motor (HTTP ${r.status}).`)}
    if(!r.ok||!d.ok)throw Error(d.error||`El motor respondió HTTP ${r.status}`);
    if(!d.image||!d.image.startsWith('data:image/png;base64,'))throw Error('El motor no devolvió un PNG válido.');
    const im=new Image();await new Promise((resolve,reject)=>{im.onload=resolve;im.onerror=()=>reject(Error('No se pudo abrir el PNG devuelto por el motor.'));im.src=d.image});
    const pc=document.createElement('canvas');pc.width=im.naturalWidth;pc.height=im.naturalHeight;const ctx=pc.getContext('2d',{willReadFrequently:true});if(!ctx)throw Error('No se pudo crear la máscara.');ctx.drawImage(im,0,0);
    if(!canvasHasVisiblePixels(pc))throw Error('La máscara salió vacía; se conserva el recorte original para revisión.');
    piece.processedCanvas=pc;piece.processedDataURL=d.image;piece.silhouetteReady=true;piece.qualityAudit=qualityAudit(pc);applyTrim(piece,d);ok++;
   }catch(err){failed.push(`${piece.name}: ${err.name==='AbortError'?'el procesamiento tardó más de 3 minutos':err.message}`)}
   draw();renderList();
  }
  if(selected>=0&&pieces[selected]){updateInspect();updateQualityReport()}
  const parts=[`Piezas generadas igual al boceto: ${ok}.`,`${skipped} fondo(s) se dejaron enteros.`];
  if(failed.length)parts.push(`Fallos (${failed.length}): ${failed.slice(0,4).join(' | ')}`);
  else parts.push('Revisa visualmente cada pieza antes de registrarla.');
  status(parts.join(' '),failed.length?'err':'ok');
 }catch(e){status('Error al generar las piezas: '+e.message,'err')}
}
$('autoGrid').onclick=()=>{if(!img){status('Primero carga una imagen.','err');return}const cols=Math.max(1,Math.min(20,+$('gridCols').value||5)),rows=Math.max(1,Math.min(20,+$('gridRows').value||3)),gap=Math.max(0,+$('gridGap').value||0),cw=img.naturalWidth/cols,ch=img.naturalHeight/rows;pieces=[];for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){const x=c*cw+gap/2,y=r*ch+gap/2,w=cw-gap,h=ch-gap;pieces.push({x,y,w,h,name:`Celda ${r+1}-${c+1}`,type:'Símbolo'})}selected=0;selectPiece(0);status(`Se propusieron ${pieces.length} recortes de cuadrícula. Revisa y ajusta las piezas antes de guardarlas.`,'ok')};$('addCrop').onclick=()=>{if(!img){status('Primero carga una imagen.','err');return}const W=img.naturalWidth,H=img.naturalHeight;addPiece(W*.25,H*.25,W*.5,H*.5,`Componente ${pieces.length+1}`);status('Recorte añadido. Arrastra dentro de la imagen para dibujar otro rectángulo.','ok')};$('clearPieces').onclick=()=>{pieces=[];selected=-1;draw();renderList();status('Se borraron los recortes de la sesión; los PNG guardados no se borraron.')};canvas.addEventListener('pointerdown',e=>{if(!img||['erase','restore'].includes($('cleanTool').value))return;canvas.setPointerCapture(e.pointerId);const p=toImagePoint(e);drag={x:p.x,y:p.y};if(selected>=0){const q=pieces[selected];if(p.x>=q.x&&p.x<=q.x+q.w&&p.y>=q.y&&p.y<=q.y+q.h)drag.moving={index:selected,dx:p.x-q.x,dy:p.y-q.y}}});canvas.addEventListener('pointermove',e=>{if(!drag||!img||['erase','restore'].includes($('cleanTool').value))return;const p=toImagePoint(e);if(drag.moving){const q=pieces[drag.moving.index];q.x=Math.max(0,Math.min(img.naturalWidth-q.w,p.x-drag.moving.dx));q.y=Math.max(0,Math.min(img.naturalHeight-q.h,p.y-drag.moving.dy));selected=drag.moving.index;draw()}else{draw();ctx.strokeStyle='#ffdf70';ctx.lineWidth=Math.max(2,canvas.width/700);ctx.setLineDash([8,5]);ctx.strokeRect(drag.x,drag.y,p.x-drag.x,p.y-drag.y);ctx.setLineDash([])}});canvas.addEventListener('pointerup',e=>{if(!drag||!img||['erase','restore'].includes($('cleanTool').value)){drag=null;return}const p=toImagePoint(e);if(!drag.moving){const x=Math.min(drag.x,p.x),y=Math.min(drag.y,p.y),w=Math.abs(p.x-drag.x),h=Math.abs(p.y-drag.y);if(w>4&&h>4)addPiece(x,y,w,h,`Componente ${pieces.length+1}`)}drag=null;draw();renderList()});$('applyName').onclick=()=>{if(selected<0)return status('Selecciona una pieza.','err');pieces[selected].name=$('pieceName').value.trim()||`Componente ${selected+1}`;pieces[selected].type=$('pieceType').value;draw();renderList();status('Nombre y tipo actualizados.','ok')};async function savePiece(i){const p=pieces[i];let data;if(p.processedCanvas){data=p.processedCanvas.toDataURL('image/png')}else if(p.processedDataURL){data=p.processedDataURL}else{const out=document.createElement('canvas');out.width=Math.round(p.w);out.height=Math.round(p.h);out.getContext('2d').drawImage(cleanCanvas.width?cleanCanvas:img,p.x,p.y,p.w,p.h,0,0,out.width,out.height);data=out.toDataURL('image/png')}const name=archivoDe(p);const r=await fetch('/api/assets/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,filename:name+'.png',mimeType:'image/png',data})});const j=await r.json();if(!r.ok)throw Error(j.error||'No se pudo guardar '+name);return j}$('saveOne').onclick=async()=>{if(selected<0)return status('Selecciona una pieza primero.','err');try{const p=pieces[selected];p.name=$('pieceName').value.trim()||p.name;p.type=$('pieceType').value;const j=await savePiece(selected);status(`Guardado en biblioteca: ${j.name}. PNG de ${Math.round(p.w)}×${Math.round(p.h)} px.`,'ok');renderList()}catch(e){status('Error al guardar: '+e.message,'err')}};$('saveAll').onclick=async()=>{if(!pieces.length)return status('No hay piezas para guardar.','err');$('saveAll').disabled=true;let ok=0,skip=[];try{for(let i=0;i<pieces.length;i++){const p=pieces[i];if(p.skipSave){skip.push(p.titleReason?`${p.name}: ${p.titleReason}`:(p.name||`Pieza ${i+1}`));continue;}if(!isBackgroundPiece(p)&&!(p.silhouetteReady&&p.processedCanvas&&canvasHasVisiblePixels(p.processedCanvas))){skip.push(p.name||`Pieza ${i+1}`);continue}await savePiece(i);ok++;status(`Guardando piezas válidas: ${ok}/${pieces.length}…`)}status(`Proceso terminado: ${ok} PNG guardados. ${skip.length} pieza(s) omitidas por no tener silueta validada${skip.length?': '+skip.slice(0,5).join(' · '):'.'}`,skip.length?'err':'ok')}catch(e){status(`Se guardaron ${ok} de ${pieces.length}. Error: ${e.message}`,'err')}finally{$('saveAll').disabled=false}};

function snapshot(){if(!img)return;try{editHistory.push(cleanCtx.getImageData(0,0,cleanCanvas.width,cleanCanvas.height));if(editHistory.length>12)editHistory.shift();redoHistory=[]}catch(e){}}
function resetClean(save=true){if(!img)return;if(save)snapshot();cleanCanvas.width=img.naturalWidth;cleanCanvas.height=img.naturalHeight;cleanCtx.clearRect(0,0,cleanCanvas.width,cleanCanvas.height);cleanCtx.drawImage(img,0,0);cleanCanvas.dataset.ready='1';if(typeof viewScale!=='undefined'&&viewScale){cleanCanvas.style.width=(img.naturalWidth*viewScale)+'px';cleanCanvas.style.height=(img.naturalHeight*viewScale)+'px'}$('cleanStatus').textContent='Imagen restaurada desde el original.';draw()}
function saveEditedBlob(name){return new Promise(resolve=>cleanCanvas.toBlob(b=>{if(!b){resolve(false);return}const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1500);resolve(true)},'image/png'))}
function magicErase(){
 if(!img){$('cleanStatus').textContent='Carga una imagen primero.';return}
 snapshot();
 const w=cleanCanvas.width,h=cleanCanvas.height,tol=Math.max(0,Math.min(150,Number($('colorTolerance').value)||35));
 const im=cleanCtx.getImageData(0,0,w,h),d=im.data,seen=new Uint8Array(w*h),stack=[];
 // Semillas distribuidas por todo el perímetro, no solo las cuatro esquinas.
 // Así puede encontrar fondos que tocan los bordes aunque las esquinas sean distintas.
 const step=Math.max(1,Math.floor(Math.min(w,h)/180));
 const seeds=[];
 for(let x=0;x<w;x+=step){seeds.push([x,0],[x,h-1])}
 for(let y=0;y<h;y+=step){seeds.push([0,y],[w-1,y])}
 const push=(x,y)=>{
  if(x<0||y<0||x>=w||y>=h)return;
  const k=y*w+x;if(seen[k])return;seen[k]=1;
  const i=k*4;if(d[i+3]===0)return;
  // Compara contra el color original del borde más cercano; evita propagar a través de colores muy distintos.
  let best=Infinity;
  for(const [sx,sy] of seeds){
   if(Math.abs(sx-x)+Math.abs(sy-y)>Math.max(w,h)*.08)continue;
   const si=(sy*w+sx)*4;
   const dist=Math.max(Math.abs(d[i]-d[si]),Math.abs(d[i+1]-d[si+1]),Math.abs(d[i+2]-d[si+2]));
   if(dist<best)best=dist;
   if(best<=tol)break;
  }
  if(best<=tol)stack.push(k);
 };
 for(const [x,y] of seeds)push(x,y);
 let removed=0;
 while(stack.length){
  const k=stack.pop(),i=k*4,x=k%w,y=Math.floor(k/w);
  if(d[i+3]===0)continue;
  d[i+3]=0;removed++;
  push(x-1,y);push(x+1,y);push(x,y-1);push(x,y+1);
 }
 cleanCtx.putImageData(im,0,0);
 $('cleanStatus').textContent=`Borrador por bordes: ${removed.toLocaleString()} píxeles pasaron a transparencia alfa. Revisa halos y zonas del objeto; usa Deshacer si se borró parte del componente.`;
}
$('removeBg').onclick=()=>{if(!img)return $('cleanStatus').textContent='Carga una imagen primero.';magicErase()};$('cleanTool').onchange=()=>{canvas.style.pointerEvents=$('cleanTool').value==='erase'||$('cleanTool').value==='restore'?'auto':'auto';$('cleanStatus').textContent=$('cleanTool').value==='erase'?'Arrastra sobre la imagen para borrar con el pincel.':$('cleanTool').value==='restore'?'Arrastra sobre la imagen para restaurar desde el original.':$('cleanTool').value==='wand'?'Usa “Quitar fondo por color” para eliminar colores conectados al borde.':'Modo de selección de recortes.'};
canvas.addEventListener('pointerdown',e=>{if(!img||!['erase','restore'].includes($('cleanTool').value))return;cleanDrag={last:toImagePoint(e)};canvas.setPointerCapture(e.pointerId);snapshot();e.preventDefault()});canvas.addEventListener('pointermove',e=>{if(!cleanDrag||!img)return;const p=toImagePoint(e),last=cleanDrag.last,sz=Math.max(1,Math.min(300,+$('brushSize').value||24));cleanCtx.save();cleanCtx.lineCap='round';cleanCtx.lineJoin='round';cleanCtx.lineWidth=sz;if($('cleanTool').value==='erase'){cleanCtx.globalCompositeOperation='destination-out';cleanCtx.strokeStyle='rgba(0,0,0,1)'}else{cleanCtx.globalCompositeOperation='source-over';cleanCtx.strokeStyle='#fff';cleanCtx.globalAlpha=1}cleanCtx.beginPath();cleanCtx.moveTo(last.x,last.y);cleanCtx.lineTo(p.x,p.y);cleanCtx.stroke();cleanCtx.restore();cleanDrag.last=p});canvas.addEventListener('pointerup',()=>{if(cleanDrag){cleanDrag=null;$('cleanStatus').textContent=$('cleanTool').value==='erase'?'Zona borrada a transparencia.':'Zona restaurada desde el original.'}});
$('undoEdit').onclick=()=>{if(!editHistory.length)return $('cleanStatus').textContent='No hay cambios que deshacer.';redoHistory.push(cleanCtx.getImageData(0,0,cleanCanvas.width,cleanCanvas.height));cleanCtx.putImageData(editHistory.pop(),0,0);$('cleanStatus').textContent='Último cambio deshecho.'};$('redoEdit').onclick=()=>{if(!redoHistory.length)return $('cleanStatus').textContent='No hay cambios que rehacer.';editHistory.push(cleanCtx.getImageData(0,0,cleanCanvas.width,cleanCanvas.height));cleanCtx.putImageData(redoHistory.pop(),0,0);$('cleanStatus').textContent='Cambio rehecho.'};$('resetEdit').onclick=()=>resetClean(true);$('erasePicked').onclick=()=>{if(selected<0||!pieces[selected])return $('cleanStatus').textContent='Selecciona una pieza primero.';snapshot();const p=pieces[selected];cleanCtx.clearRect(p.x,p.y,p.w,p.h);$('cleanStatus').textContent='Se borró el área de la pieza seleccionada a transparencia.'};$('exportClean').onclick=async()=>{if(!img)return $('cleanStatus').textContent='Carga una imagen primero.';const ok=await saveEditedBlob(sourceName+'_editada.png');$('cleanStatus').textContent=ok?'PNG editado exportado.':'No se pudo exportar el PNG.'};

if(!runsOnStudio()){const note=$('whereToRun');if(note){note.hidden=false;note.style.color='var(--gold)';note.textContent=studioRequiredMessage()}}
