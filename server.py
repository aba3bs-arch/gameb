#!/usr/bin/env python3
'Servidor local GAMEB Studio. Sign in with ChatGPT (OAuth) para uso elegible del plan; API key opcional solo como respaldo.'
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os, socket, json, base64, io, zipfile, urllib.request, urllib.error, urllib.parse, re, time, secrets, hashlib, threading, webbrowser, uuid, datetime
ROOT=Path(__file__).resolve().parent
ASSET_DIR=ROOT/'assets'/'imported'
ASSET_DIR.mkdir(parents=True,exist_ok=True)
try:
 from PIL import Image
except Exception: Image=None

# Reutiliza la sesión de segmentación para evitar inicializar el modelo en cada recorte.
_REMBG_SESSION = None
_REMBG_SESSION_LOCK = threading.Lock()

def _get_rembg_session(new_session):
    """Inicializa una única sesión de rembg bajo bloqueo; no oculta errores del modelo."""
    global _REMBG_SESSION
    with _REMBG_SESSION_LOCK:
        if _REMBG_SESSION is not None:
            return _REMBG_SESSION
        session = new_session('u2net')
        if session is None:
            raise RuntimeError('rembg no pudo crear la sesión u2net.')
        _REMBG_SESSION = session
        return session

def decode_data(data):
 if not isinstance(data,str) or ',' not in data: raise ValueError('Imagen no válida')
 head,b64=data.split(',',1); return head,base64.b64decode(b64)
def fallback_components(width=1000,height=600,cols=5,rows=3):
 items=[{'id':'background','name':'Fondo principal','type':'Fondo','x':0,'y':0,'w':width,'h':height,'confidence':0.35}, {'id':'title','name':'Título / logotipo','type':'Título / logo','x':int(width*.28),'y':int(height*.02),'w':int(width*.44),'h':int(height*.13),'confidence':0.25},{'id':'reels_frame','name':'Marco de rodillos','type':'Marco de rodillos','x':int(width*.25),'y':int(height*.2),'w':int(width*.5),'h':int(height*.55),'confidence':0.25}]
 cw=width*.5/cols; ch=height*.55/rows
 for r in range(rows):
  for c in range(cols): items.append({'id':f'cell_{r*cols+c+1}','name':f'Celda {r*cols+c+1}','type':'Símbolo','x':int(width*.25+c*cw),'y':int(height*.2+r*ch),'w':int(cw),'h':int(ch),'confidence':0.2})
 items += [{'id':'jackpot_grand','name':'Jackpot GRAND','type':'Jackpot','x':int(width*.04),'y':int(height*.1),'w':int(width*.18),'h':int(height*.1),'confidence':0.2},{'id':'spin_button','name':'Botón girar','type':'Botón','x':int(width*.78),'y':int(height*.78),'w':int(width*.16),'h':int(height*.15),'confidence':0.2},{'id':'credits_counter','name':'Contador de créditos','type':'Contador','x':int(width*.38),'y':int(height*.85),'w':int(width*.22),'h':int(height*.08),'confidence':0.2}]
 return items

# Credenciales OAuth se guardan localmente, no en la carpeta pública del proyecto.
APPDATA = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'GAMEBStudio'
APPDATA.mkdir(parents=True, exist_ok=True)
CREDENTIALS_FILE = APPDATA / 'chatgpt_credentials.json'
HOST_FILE = APPDATA / 'host_id.txt'
try:
 HOST_ID = HOST_FILE.read_text(encoding='utf-8').strip()
except Exception:
 HOST_ID = ''
if not HOST_ID:
 HOST_ID = 'urn:uuid:' + str(uuid.uuid4())
 try: HOST_FILE.write_text(HOST_ID, encoding='utf-8')
 except Exception: pass
OAUTH_PENDING = {}
OAUTH_LOCK = threading.Lock()
OAUTH_SCOPES = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
OAUTH_RESOURCE = 'https://api.openai.com/v1'
OAUTH_REDIRECT = 'http://127.0.0.1:8766/auth/callback'

def read_credentials():
 try:
  d=json.loads(CREDENTIALS_FILE.read_text(encoding='utf-8'))
  return d if isinstance(d,dict) else {}
 except Exception: return {}
def save_credentials(d):
 tmp=CREDENTIALS_FILE.with_suffix('.tmp')
 tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
 try: os.chmod(tmp,0o600)
 except Exception: pass
 tmp.replace(CREDENTIALS_FILE)
def b64url(b): return base64.urlsafe_b64encode(b).decode().rstrip('=')
def oauth_authorize_url():
 state=secrets.token_urlsafe(32); nonce=secrets.token_urlsafe(32); verifier=b64url(secrets.token_bytes(48)); challenge=b64url(hashlib.sha256(verifier.encode()).digest())
 creds=read_credentials(); issued=creds.get('client_id')
 q={'client_id':issued or 'dynamic_agent_client','response_type':'code','redirect_uri':OAUTH_REDIRECT,'scope':OAUTH_SCOPES,'resource':OAUTH_RESOURCE,'state':state,'nonce':nonce,'code_challenge_method':'S256','code_challenge':challenge,'ext_agent_host_id':HOST_ID}
 if not issued: q['agent_name_hint']='GAMEB Studio'
 elif creds.get('id_token'): q['id_token_hint']=creds['id_token']
 elif creds.get('email'): q['login_hint']=creds['email']
 with OAUTH_LOCK: OAUTH_PENDING[state]={'state':state,'nonce':nonce,'verifier':verifier,'redirect_uri':OAUTH_REDIRECT,'client_id':issued,'created':time.time()}
 return 'https://auth.openai.com/api/accounts/authorize?'+urllib.parse.urlencode(q)
def token_post(payload):
 req=urllib.request.Request('https://auth.openai.com/api/accounts/oauth/token',data=urllib.parse.urlencode(payload).encode(),headers={'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json'},method='POST')
 try:
  with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode())
 except urllib.error.HTTPError as e: raise RuntimeError('Intercambio OAuth HTTP '+str(e.code)+': '+e.read().decode()[:400])
def validate_id_token(id_token, client_id, nonce):
 try:
  import jwt
  discovery_req=urllib.request.Request('https://auth.openai.com/.well-known/openid-configuration',headers={'Accept':'application/json'})
  with urllib.request.urlopen(discovery_req,timeout=20) as r: discovery=json.loads(r.read().decode())
  jwks=jwt.PyJWKClient(discovery['jwks_uri'])
  signing_key=jwks.get_signing_key_from_jwt(id_token).key
  claims=jwt.decode(id_token,signing_key,algorithms=['RS256','ES256'],audience=client_id,issuer='https://auth.openai.com',options={'require':['exp','iat','iss','aud','sub']})
  if claims.get('nonce') != nonce: raise RuntimeError('El nonce de seguridad no coincide.')
  return claims
 except ImportError:
  raise RuntimeError('Falta la dependencia de validación segura. Ejecuta INSTALAR_DEPENDENCIAS.bat.')
 except Exception as e:
  raise RuntimeError('No se pudo validar el ID token de OpenAI: '+str(e))
def finish_oauth(query):
 state=query.get('state',[''])[0]
 with OAUTH_LOCK: pending=OAUTH_PENDING.pop(state,None)
 if not pending or time.time()-pending['created']>600: raise RuntimeError('Autorización vencida o state inválido. Vuelve a pulsar Conectar con ChatGPT.')
 if query.get('error'): raise RuntimeError('OpenAI no completó la autorización: '+query.get('error',['error'])[0])
 code=query.get('code',[''])[0]
 client_id=query.get('client_id',[pending.get('client_id') or ''])[0]
 if not code or not client_id: raise RuntimeError('La respuesta OAuth no incluyó code/client_id. Intenta conectar otra vez.')
 if pending.get('client_id') and client_id!=pending['client_id']: raise RuntimeError('El client_id devuelto no coincide con la cuenta elegida.')
 data=token_post({'grant_type':'authorization_code','client_id':client_id,'code':code,'code_verifier':pending['verifier'],'redirect_uri':pending['redirect_uri'],'resource':OAUTH_RESOURCE})
 granted=set((data.get('scope') or query.get('scope',[''])[0]).split())
 if not data.get('id_token'): raise RuntimeError('OpenAI no devolvió un ID token; no se guardaron credenciales.')
 claims=validate_id_token(data['id_token'],client_id,pending['nonce'])
 if 'chatgpt.tokens.use.direct' not in granted:
  raise RuntimeError('Conectaste la identidad, pero no autorizaste el uso del plan ChatGPT. Vuelve a conectar y acepta ese permiso si está disponible.')
 creds={'client_id':client_id,'subject':claims.get('sub'),'email':claims.get('email',''),'name':claims.get('name',''),'id_token':data['id_token'],'access_token':data.get('access_token',''),'refresh_token':data.get('refresh_token',''),'token_type':data.get('token_type','Bearer'),'expires_at':time.time()+int(data.get('expires_in',3600))-60,'scopes':sorted(granted),'ext_agent_host_id':HOST_ID,'saved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 if not creds['access_token']: raise RuntimeError('OpenAI no devolvió access_token.')
 save_credentials(creds)
 return creds
def access_token():
 creds=read_credentials()
 if not creds.get('access_token'): return None
 if float(creds.get('expires_at',0)) > time.time()+30: return creds['access_token']
 refresh=creds.get('refresh_token')
 if not refresh: return None
 data=token_post({'grant_type':'refresh_token','client_id':creds['client_id'],'refresh_token':refresh,'resource':OAUTH_RESOURCE})
 scopes=set((data.get('scope') or ' '.join(creds.get('scopes',[]))).split())
 if 'chatgpt.tokens.use.direct' not in scopes: raise RuntimeError('El token renovado no incluye permiso de uso del plan ChatGPT.')
 creds.update({'access_token':data.get('access_token',creds['access_token']),'refresh_token':data.get('refresh_token',refresh),'expires_at':time.time()+int(data.get('expires_in',3600))-60,'scopes':sorted(scopes),'saved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
 save_credentials(creds)
 return creds['access_token']
_MODEL_CACHE = {}
def choose_model(token, preferred='gpt-4.1-mini', use_chatgpt_plan=True):
 # Sign-in with ChatGPT requires selecting a model from this account's catalog.
 # Cache the catalog briefly to avoid a network round-trip on every prompt.
 import hashlib, time
 cache_key=hashlib.sha256(token.encode()).hexdigest()[:16]
 cached=_MODEL_CACHE.get(cache_key)
 now=time.time()
 if cached and now-cached[0] < 600:
  models=cached[1]
 else:
  req=urllib.request.Request('https://api.openai.com/v1/models',headers={'Authorization':'Bearer '+token,'Accept':'application/json'},method='GET')
  try:
   with urllib.request.urlopen(req,timeout=12) as r: data=json.loads(r.read().decode('utf-8','replace'))
  except urllib.error.HTTPError as e:
   body=e.read().decode(errors='replace')[:300]
   raise RuntimeError('No se pudo consultar el catálogo de modelos de esta cuenta (HTTP '+str(e.code)+'): '+body)
  except Exception as e:
   raise RuntimeError('No se pudo consultar el catálogo de modelos: '+str(e))
  raw=data.get('models',[]) if isinstance(data,dict) else []
  models=[m.get('slug') for m in raw if isinstance(m,dict) and m.get('slug') and m.get('visibility')=='list']
  if not models:
   # Some compatible model catalog responses expose a conventional data list.
   models=[m.get('id') for m in data.get('data',[]) if isinstance(m,dict) and m.get('id')]
  if not models: raise RuntimeError('El catálogo de esta cuenta no devolvió modelos disponibles. Revisa la autorización de ChatGPT.')
  _MODEL_CACHE[cache_key]=(now,models)
 if use_chatgpt_plan:
  # Preserve account's server-provided order; first listed model is currently offered to this account.
  return models[0]
 return preferred if preferred in models else models[0]

def openai_response(payload, token):
 payload['store']=False; payload['stream']=True
 req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'text/event-stream'},method='POST')
 try:
  with urllib.request.urlopen(req,timeout=45) as r:
   chunks=[]
   for rawline in r:
    line=rawline.decode('utf-8','replace').strip()
    if not line.startswith('data:'): continue
    raw=line[5:].strip()
    if not raw or raw=='[DONE]': continue
    try: event=json.loads(raw)
    except Exception: continue
    typ=event.get('type')
    if typ=='response.output_text.delta': chunks.append(event.get('delta',''))
    elif typ=='response.failed':
     err=event.get('response',{}).get('error') or event.get('error') or {}
     raise RuntimeError('Respuesta de ChatGPT falló: '+str(err.get('code') or err.get('message') or 'error'))
    elif typ=='error': raise RuntimeError('Error de ChatGPT: '+str(event.get('message') or event.get('code') or 'error'))
    elif typ=='response.completed': return ''.join(chunks)
   raise RuntimeError('El flujo de ChatGPT terminó sin response.completed.')
 except urllib.error.HTTPError as e:
  body=e.read().decode(errors='replace')[:700]
  if 'subscription_sharing_usage_limit_exceeded' in body or 'subscription_sharing_usage_unavailable' in body: raise RuntimeError('El uso incluido de ChatGPT no está disponible o llegó a su límite. Revisa los límites de la app en Configuración de ChatGPT.')
  raise RuntimeError('OpenAI respondió HTTP '+str(e.code)+': '+body)
 except (TimeoutError, socket.timeout) as e:
  raise RuntimeError('La solicitud a ChatGPT tardó más de 60 segundos y se canceló. Revisa tu internet y vuelve a intentar.')
 except urllib.error.URLError as e:
  raise RuntimeError('No se pudo conectar con ChatGPT: '+str(getattr(e,'reason',e)))
def analyze_with_openai(image_data, name, cols, rows, notes):
 token=access_token()
 auth_mode='chatgpt'
 if not token:
  key=os.environ.get('OPENAI_API_KEY','').strip()
  if not key: return None
  token=key;auth_mode='api'
 head,raw=decode_data(image_data)
 mime=head.split(':',1)[1].split(';',1)[0] if head.startswith('data:') else 'image/png'
 prompt=f"""Actúa como un sistema profesional de segmentación de assets para videojuegos. Analiza toda la imagen primero e identifica cada componente visible por separado. Devuelve SOLO JSON válido con shape {{"summary":"...","components":[{{"id":"snake_case","name":"nombre español","type":"Fondo|Título / logo|Marco de rodillos|Símbolo|Jackpot|Botón|Contador|Panel|Bonus|Decoración|Efecto|Otro","x":int,"y":int,"w":int,"h":int,"confidence":0.0}}]}}. Coordenadas en píxeles de la imagen original. REGLAS OBLIGATORIAS: (1) Si dos objetos se tocan o están muy juntos, NO los unas en una sola pieza: crea una caja independiente por objeto, aunque sus cajas se solapen un poco. (2) La caja debe abarcar el COMPONENTE VISUAL COMPLETO, no solo el texto o la parte central: para títulos/logos tipo letrero incluye letras, marco ornamental, flores, sombreros, puntas, sombras y decoración superior e inferior que formen parte del mismo letrero. Primero localiza el objeto semánticamente y luego estima sus límites externos; no uses el rectángulo ajustado a las letras como caja del letrero. Deja margen de análisis de 4-8% del tamaño del objeto cuando haya espacio. Nunca cortes la silueta para evitar al vecino. (2a) En títulos grandes, compara los extremos superiores/inferiores y laterales del marco completo; si los adornos sobresalen de la zona de texto, deben quedar dentro de la misma caja del título. No incluyas jackpots vecinos ni el paisaje detrás. (3) No uses una caja enorme que incluya varios componentes distintos. (4) Identifica y separa primero las piezas de primer plano (títulos, jackpots, símbolos, botones, marcos, números y adornos); trata el fondo/escena como una capa independiente al final. (5) En grupos de símbolos repetidos, devuelve una caja por símbolo si sus límites son discernibles; no combines símbolos adyacentes. (6) Si una frontera no puede determinarse con seguridad, conserva la caja individual más razonable y baja confidence; explica la incertidumbre en summary en vez de fusionar objetos. (6a) Antes de devolver el JSON, realiza una segunda comprobación de cada caja: ¿incluye todo el contorno decorativo visible del componente o solo su contenido central? Corrige la caja si faltan puntas, marco o adornos. La caja es provisional; la máscara se valida después y no se debe declarar completa solo porque el objeto fue identificado. (7) No inventes píxeles ocultos ni digas que reconstruiste lo tapado. Detecta fondo, título, marco, símbolos, jackpots, botones, contadores, paneles y bonus cuando sean visibles. Columna/filas esperadas {cols}x{rows}. Nombre del juego: {name or 'sin nombre'}. Notas adicionales: {notes}. Máximo 80 componentes. Si la imagen es boceto, identifica regiones propuestas, no afirmes que son PNG ya extraídos."""
 body={'model':choose_model(token),'input':[{'role':'user','content':[{'type':'input_text','text':prompt},{'type':'input_image','image_url':image_data,'detail':'high'}]}],'text':{'format':{'type':'json_object'}}}
 outtext=openai_response(body,token)
 parsed=json.loads(outtext)
 W=1000;H=600
 if Image:
  im=Image.open(io.BytesIO(raw));W,H=im.size
 comps=[]
 for i,c in enumerate(parsed.get('components',[])[:80]):
  try:
   x=max(0,min(W,int(c.get('x',0))));y=max(0,min(H,int(c.get('y',0))));w=max(1,min(W-x,int(c.get('w',1))));h=max(1,min(H-y,int(c.get('h',1))))
   comps.append({'id':re.sub('[^a-zA-Z0-9_]+','_',str(c.get('id') or f'component_{i+1}')).strip('_')[:60] or f'component_{i+1}','name':str(c.get('name') or f'Componente {i+1}')[:100],'type':c.get('type') if c.get('type') in ['Fondo','Título / logo','Marco de rodillos','Símbolo','Jackpot','Botón','Contador','Panel','Bonus','Decoración','Efecto','Otro'] else 'Otro','x':x,'y':y,'w':w,'h':h,'confidence':max(0,min(1,float(c.get('confidence',.5))))})
  except Exception: pass
 return {'summary':str(parsed.get('summary','Análisis terminado. Revisa todas las cajas antes de extraer.')),'components':comps,'aiUsed':True,'authMode':auth_mode,'imageWidth':W,'imageHeight':H}



def inspect_crop_with_openai(image_data, name, category, notes):
 token=access_token()
 auth_mode='chatgpt'
 if not token:
  token=os.environ.get('OPENAI_API_KEY','').strip()
  auth_mode='api'
  if not token:
   raise RuntimeError('La inspección IA necesita una sesión de ChatGPT compatible o OPENAI_API_KEY configurada en el servidor. El recorte no se envió ni se modificó.')
 head,raw=decode_data(image_data)
 mime=head.split(':',1)[1].split(';',1)[0] if head.startswith('data:') else 'image/png'
 prompt=f'''Eres un inspector visual de componentes gráficos para videojuegos. Examina ÚNICAMENTE el recorte adjunto, no imagines detalles que no se ven. Nombre: {name or 'Componente sin nombre'}. Categoría declarada: {category or 'Sin categoría'}. Instrucciones del usuario: {notes or 'Revisión general de calidad visual'}.
Busca problemas que sí sean visibles: bordes cortados, restos de fondo, halos, manchas, transparencias accidentales, deformación, desenfoque, baja resolución, márgenes desiguales, partes faltantes, texto/números residuales o elementos ajenos. Distingue defectos confirmados de posibles riesgos. Si el fondo cuadriculado/transparente no puede deducirse con certeza de la imagen, dilo. No cambies ni reconstruyas la imagen. Devuelve SOLO JSON válido con esta forma exacta: {{"summary":"resumen en español","quality":"Correcto|Revisar|Defectos detectados","issues":[{{"severity":"Alta|Media|Baja|Observación","title":"problema breve","detail":"qué se ve y dónde","recommendation":"acción concreta sin alterar el diseño original"}}],"strengths":["aspecto que está bien"],"ready_to_register":false,"confidence":0.0}}. Incluye máximo 8 problemas, evita falsos positivos y usa lista vacía si no encuentras problemas claros. ready_to_register debe ser true solo si no hay defectos relevantes visibles; la decisión final siempre pertenece al usuario.'''
 body={'model':choose_model(token),'input':[{'role':'user','content':[{'type':'input_text','text':prompt},{'type':'input_image','image_url':image_data,'detail':'high'}]}],'text':{'format':{'type':'json_object'}}}
 parsed=json.loads(openai_response(body,token))
 issues=parsed.get('issues',[])
 if not isinstance(issues,list): issues=[]
 clean=[]
 for item in issues[:8]:
  if not isinstance(item,dict): continue
  sev=item.get('severity','Observación')
  if sev not in ['Alta','Media','Baja','Observación']: sev='Observación'
  clean.append({'severity':sev,'title':str(item.get('title','Detalle visual'))[:120],'detail':str(item.get('detail',''))[:600],'recommendation':str(item.get('recommendation',''))[:600]})
 strengths=parsed.get('strengths',[])
 if not isinstance(strengths,list): strengths=[]
 return {'ok':True,'summary':str(parsed.get('summary','Inspección terminada.'))[:1200], 'quality':parsed.get('quality') if parsed.get('quality') in ['Correcto','Revisar','Defectos detectados'] else ('Defectos detectados' if clean else 'Revisar'), 'issues':clean,'strengths':[str(x)[:300] for x in strengths[:6]],'ready_to_register':bool(parsed.get('ready_to_register',False)),'confidence':max(0,min(1,float(parsed.get('confidence',.5)))),'model':choose_model(token),'authMode':auth_mode,'imageBytes':len(raw),'mimeType':mime}

def generate_sketch_with_openai(name, theme, style, concept, cols, rows, notes):
 token=access_token()
 auth_mode='chatgpt'
 if not token:
  key=os.environ.get('OPENAI_API_KEY','').strip()
  if not key: raise RuntimeError('No hay sesión de ChatGPT activa. Conecta tu cuenta en la etapa 4.')
  token=key;auth_mode='api'
 prompt=f"""Crea un boceto visual original de una tragamonedas en SVG autocontenido de 1000x600 píxeles. Es un concepto de interfaz ficticia, sin dinero real. Juego: {name or 'Juego nuevo'}. Tema: {theme or 'Aventura fantástica'}. Estilo visual: {style or 'Moderno premium'}. Idea del usuario: {concept or 'Diseño atractivo y legible'}. Rodillos: {cols} columnas x {rows} filas. Notas: {notes or 'Sin notas adicionales'}.
Devuelve SOLO el SVG completo, sin markdown ni explicaciones. Usa viewBox="0 0 1000 600", fondo elaborado, título legible, un marco central con exactamente {cols} columnas y {rows} filas, símbolos vectoriales sencillos originales, paneles de jackpot arriba y controles abajo. Composición equilibrada, bordes limpios, sin elementos fuera del lienzo, textos cortos en español, contraste alto, estética pulida. Usa solo SVG y formas vectoriales (rect, path, circle, ellipse, polygon, text, defs/linearGradient). No uses scripts, enlaces, imágenes externas, foreignObject ni filtros costosos. Debe ser SVG válido y cerrar todos los tags."""
 body={'model':choose_model(token, use_chatgpt_plan=(auth_mode=='chatgpt')),'input':[{'role':'user','content':[{'type':'input_text','text':prompt}]}]}
 out=openai_response(body,token).strip()
 out=re.sub(r'^```(?:svg|xml)?\s*','',out,flags=re.I);out=re.sub(r'\s*```$','',out)
 start=out.find('<svg');end=out.rfind('</svg>')
 if start<0 or end<0: raise RuntimeError('La IA no devolvió un SVG válido. Intenta con una idea más corta.')
 svg=out[start:end+6]
 if len(svg)>2_000_000: raise RuntimeError('El boceto generado es demasiado grande.')
 low=svg.lower()
 if any(x in low for x in ['<script','javascript:','<foreignobject','<iframe','<image',' onload=',' onclick=']) or re.search(r'\b(?:href|xlink:href|src)\s*=\s*[\"\']\s*(?:https?:|//|data:)',svg,re.I):
  raise RuntimeError('El SVG generado contenía elementos no permitidos; vuelve a generar.')
 if not re.search(r'<svg\b',svg) or not re.search(r'</svg>',svg): raise RuntimeError('SVG incompleto.')
 return {'ok':True,'svg':svg,'authMode':auth_mode,'summary':'Boceto vectorial generado con IA. Revísalo y edítalo antes de usarlo como referencia.'}

class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
 def log_message(self,*args): pass
 def send_json(self,code,obj):
  b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.send_header('Access-Control-Allow-Origin','*');self.end_headers();self.wfile.write(b)
 def do_POST(self):
  try:
   n=int(self.headers.get('Content-Length','0'))
   if n>35_000_000: return self.send_json(413,{'error':'Solicitud demasiado grande; reduce el tamaño de la imagen.'})
   data=json.loads(self.rfile.read(n).decode())
   if self.path=='/api/assets/import':
    name=str(data.get('name','componente')).strip()[:100] or 'componente'
    mime=str(data.get('mimeType',''))
    if mime not in ('image/png','image/jpeg','image/webp'): return self.send_json(400,{'error':'Formato no admitido. Usa PNG, JPG o WebP.'})
    head,raw=decode_data(data.get('data',''))
    if len(raw)>15*1024*1024: return self.send_json(413,{'error':'La imagen supera 15 MB.'})
    if not head.lower().startswith('data:'+mime): return self.send_json(400,{'error':'El tipo MIME no coincide con el archivo.'})
    ext={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp'}[mime]
    slug=re.sub(r'[^a-zA-Z0-9_-]+','_',name).strip('_')[:70] or 'componente'
    filename=slug+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+ext
    target=(ASSET_DIR/filename).resolve()
    if ASSET_DIR.resolve() not in target.parents: return self.send_json(400,{'error':'Nombre de archivo no válido.'})
    target.write_bytes(raw)
    return self.send_json(200,{'ok':True,'name':name,'filename':filename,'url':'/assets/imported/'+urllib.parse.quote(filename),'bytes':len(raw),'type':mime})
   if self.path=='/api/assets/delete':
    filename=str(data.get('filename',''))
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:png|jpg|webp)',filename,re.I): return self.send_json(400,{'error':'Nombre de archivo no válido.'})
    target=(ASSET_DIR/filename).resolve()
    if ASSET_DIR.resolve() not in target.parents: return self.send_json(400,{'error':'Ruta no válida.'})
    if not target.is_file(): return self.send_json(404,{'error':'El componente no existe.'})
    target.unlink();return self.send_json(200,{'ok':True})
   if self.path=='/api/auth/start':
    url=oauth_authorize_url();return self.send_json(200,{'ok':True,'url':url,'method':'Sign in with ChatGPT'})
   if self.path=='/api/auth/disconnect':
    try: CREDENTIALS_FILE.unlink(missing_ok=True)
    except Exception: pass
    return self.send_json(200,{'ok':True,'connected':False})
   if self.path=='/api/assistant-stream':
    token=access_token()
    mode='chatgpt'
    if not token:
     token=os.environ.get('OPENAI_API_KEY','').strip()
     mode='api'
    if not token: return self.send_json(401,{'error':'No hay sesión ChatGPT activa ni API key configurada.'})
    messages=data.get('messages',[])
    if not isinstance(messages,list): return self.send_json(400,{'error':'El historial debe ser una lista.'})
    clean=[]
    for m in messages[-12:]:
     if not isinstance(m,dict) or m.get('role') not in ('user','assistant'): continue
     content=str(m.get('content',''))[:5000]
     if content: clean.append({'role':m['role'],'content':content})
    if not clean or clean[-1]['role']!='user': return self.send_json(400,{'error':'Escribe una orden antes de enviar.'})
    system_prompt=("Eres GAMEB Studio, asistente técnico en español para crear prototipos de tragamonedas de demostración. "
    "Trabaja como un copiloto: entiende órdenes, haz preguntas solo si faltan datos esenciales, resume acciones concretas. "
    "No afirmes que has editado archivos ni probado el juego si no se ejecutó una herramienta real. "
    "Distingue boceto visual, matemática de demostración y juego probado. La matemática y RTP deben validarse con simulaciones antes de considerarse fiables. "
    "Cuando el usuario pida diseñar, devuelve un plan claro y una especificación estructurada en texto; no inventes acceso a archivos.")
    body={'model':choose_model(token, use_chatgpt_plan=(mode=='chatgpt')),'instructions':system_prompt,'input':clean,'stream':True,'store':False}
    try:
     req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'text/event-stream'},method='POST')
     with urllib.request.urlopen(req,timeout=60) as upstream:
      self.send_response(200);self.send_header('Content-Type','text/event-stream; charset=utf-8');self.send_header('Cache-Control','no-cache, no-transform');self.send_header('Connection','close');self.end_headers()
      for rawline in upstream:
       line=rawline.decode('utf-8','replace').strip()
       if not line.startswith('data:'): continue
       raw= line[5:].strip()
       if not raw or raw=='[DONE]': continue
       try: ev=json.loads(raw)
       except Exception: continue
       typ=ev.get('type')
       if typ=='response.output_text.delta':
        packet=json.dumps({'type':'delta','text':ev.get('delta','')},ensure_ascii=False)
        self.wfile.write(('data: '+packet+'\n\n').encode());self.wfile.flush()
       elif typ in ('response.failed','error'):
        er=ev.get('response',{}).get('error') or ev.get('error') or {}
        msg=str(er.get('message') or er.get('code') or ev.get('message') or 'Error del modelo')
        packet=json.dumps({'type':'error','message':msg},ensure_ascii=False)
        self.wfile.write(('data: '+packet+'\n\n').encode());self.wfile.flush()
       elif typ=='response.completed':
        packet=json.dumps({'type':'done','mode':mode},ensure_ascii=False)
        self.wfile.write(('data: '+packet+'\n\n').encode());self.wfile.flush()
      return
    except urllib.error.HTTPError as e:
     bodyerr=e.read().decode(errors='replace')[:500]
     if 'subscription_sharing_usage_limit_exceeded' in bodyerr or 'subscription_sharing_usage_unavailable' in bodyerr: msg='El uso del plan ChatGPT no está disponible o llegó a su límite.'
     else: msg='Error HTTP '+str(e.code)+': '+bodyerr
     return self.send_json(502,{'error':msg})
    except Exception as e:
     return self.send_json(502,{'error':'No se pudo iniciar el flujo: '+str(e)})
   if self.path=='/api/generate-image':
    return self.send_json(410,{'error':'La generación de imágenes no está disponible mediante la conexión compartida de ChatGPT. Diseña el boceto en ChatGPT y usa /api/assets/import para incorporarlo a la biblioteca local.'})
   if self.path=='/api/generate-sketch':
    try:
     result=generate_sketch_with_openai(str(data.get('name',''))[:120],str(data.get('theme',''))[:120],str(data.get('style',''))[:120],str(data.get('concept',''))[:2500],max(3,min(6,int(data.get('columns',5)))),max(3,min(5,int(data.get('rows',3)))),str(data.get('notes',''))[:1500])
    except Exception as e: return self.send_json(502,{'error':str(e)})
    return self.send_json(200,result)
   if self.path=='/api/remove-background':
    global _REMBG_SESSION
    try:
     if Image is None: return self.send_json(503,{'ok':False,'error':'Falta Pillow. Instala las dependencias del proyecto.'})
     try:
      from rembg import remove, new_session
     except Exception as imp_err:
      return self.send_json(503,{'ok':False,'error':'No se pudo cargar rembg/onnxruntime. Ejecuta INSTALAR_DEPENDENCIAS.bat, espera a que termine sin errores y reinicia GAMEB Studio. Detalle: '+str(imp_err)[:180]})
     head,raw=decode_data(data.get('image',''))
     if len(raw)>15*1024*1024: return self.send_json(413,{'ok':False,'error':'El recorte supera 15 MB.'})
     source=Image.open(io.BytesIO(raw)).convert('RGBA')
     if source.width < 2 or source.height < 2: return self.send_json(400,{'ok':False,'error':'El recorte está vacío o sus dimensiones no son válidas.'})
     session = _get_rembg_session(new_session)
     # Primero intenta alpha matting para mejorar bordes finos y semitransparentes.
     # Si pymatting no está disponible o falla, usa la máscara estándar sin bloquear el flujo.
     engine='rembg-u2net-alpha-matting'
     try:
      result=remove(source, session=session, alpha_matting=True,
                    alpha_matting_foreground_threshold=240,
                    alpha_matting_background_threshold=10,
                    alpha_matting_erode_size=10)
     except Exception:
      engine='rembg-u2net-standard-fallback'
      result=remove(source, session=session, alpha_matting=False)
     if not isinstance(result,Image.Image): result=Image.open(io.BytesIO(result)).convert('RGBA')
     else: result=result.convert('RGBA')
     result=result.convert('RGBA')
     # Refinamiento conservador de alfa: suaviza solo el borde para evitar dientes
     # sin recortar la pieza ni cambiar sus dimensiones originales.
     try:
      from PIL import ImageFilter
      alpha=result.getchannel('A')
      alpha=alpha.filter(ImageFilter.GaussianBlur(radius=0.45))
      result.putalpha(alpha)
     except Exception: pass
     alpha=result.getchannel('A')
     extrema=alpha.getextrema()
     if extrema[1] < 8:
      raise RuntimeError('La máscara quedó prácticamente vacía; no se exportó una silueta incorrecta.')
     out=io.BytesIO();result.save(out,format='PNG',optimize=True)
     encoded=base64.b64encode(out.getvalue()).decode('ascii')
     return self.send_json(200,{'ok':True,'image':'data:image/png;base64,'+encoded,'width':result.width,'height':result.height,'engine':engine,'alphaMatting':engine.endswith('alpha-matting')})
    except Exception as e: return self.send_json(502,{'ok':False,'error':'Falló la segmentación: '+str(e)[:300]})
   if self.path=='/api/inspect-crop':
    try:
     result=inspect_crop_with_openai(str(data.get('image','')),str(data.get('name',''))[:120],str(data.get('category',''))[:80],str(data.get('notes',''))[:1200])
     return self.send_json(200,result)
    except Exception as e:
     return self.send_json(502,{'ok':False,'error':str(e)})
   if self.path=='/api/analyze':
    head,raw=decode_data(data.get('image',''))
    W,H=1000,600
    if Image:
     im=Image.open(io.BytesIO(raw));W,H=im.size
    try: result=analyze_with_openai(data.get('image',''),data.get('name',''),int(data.get('columns',5)),int(data.get('rows',3)),data.get('notes',''))
    except Exception as e: return self.send_json(502,{'error':str(e)})
    if result is None: result={'summary':'No hay OPENAI_API_KEY en el entorno. Se muestra una plantilla geométrica de respaldo, no una detección IA. Ajusta las cajas manualmente.','components':fallback_components(W,H,int(data.get('columns',5)),int(data.get('rows',3))),'aiUsed':False,'imageWidth':W,'imageHeight':H}
    return self.send_json(200,result)
   if self.path=='/api/export':
    payload=data;proj=payload.get('project',{});assets=payload.get('assets',{});name=re.sub(r'[^a-zA-Z0-9_-]+','_',proj.get('name','GAMEB_JUEGO')).strip('_') or 'GAMEB_JUEGO'
    mem=io.BytesIO();z=zipfile.ZipFile(mem,'w',zipfile.ZIP_DEFLATED)
    def put(path,content): z.writestr(name+'/'+path,content if isinstance(content,bytes) else str(content).encode())
    sketch=assets.get('sketch','');components=proj.get('components',[]);symbol_list=proj.get('symbols',[])
    if sketch:
     try:
      _,raw=decode_data(sketch);put('assets/reference/sketch_original.png' if 'png' in sketch[:40] else 'assets/reference/sketch_original.bin',raw)
     except Exception: pass
    put('project.json',json.dumps(payload,ensure_ascii=False,indent=2))
    put('manifest.json',json.dumps({'schemaVersion':1,'game':name,'components':components,'symbols':symbol_list,'notes':'Bounding boxes require human review. Crops from a composite screenshot may contain neighboring pixels.','motion':proj.get('motion',{})},ensure_ascii=False,indent=2))
    crop_count=0
    if sketch and Image:
     try:
      _,raw=decode_data(sketch);im=Image.open(io.BytesIO(raw)).convert('RGBA');W,H=im.size
      for i,c in enumerate(components):
       try:
        x=max(0,min(W,int(c.get('x',0))));y=max(0,min(H,int(c.get('y',0))));w=max(1,min(W-x,int(c.get('w',1))));h=max(1,min(H-y,int(c.get('h',1))))
        crop=im.crop((x,y,x+w,y+h));buf=io.BytesIO();crop.save(buf,format='PNG');slug=re.sub(r'[^a-zA-Z0-9_-]+','_',c.get('id') or f'component_{i+1}').strip('_')
        put(f'assets/extracted/{slug}.png',buf.getvalue());crop_count+=1
       except Exception: pass
     except Exception: pass
    game_html='''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GAMEB Prototype</title><link rel="stylesheet" href="style.css"></head><body><main><header><h1 id="title">GAMEB Prototype</h1><p>Prototipo local · matemática de demostración</p></header><section class="reels" id="reels"></section><section class="stats"><div>Apuesta <b id="bet">$0.10</b></div><div>Créditos <b id="credits">$100.00</b></div><div>Ganancia <b id="win">$0.00</b></div></section><div class="controls"><button id="betDown">−</button><button id="betUp">+</button><button id="spin">GIRAR</button><button id="turbo">TURBO: OFF</button></div><p id="status">Demo: los resultados y pagos no son matemáticas reales.</p><details><summary>Auditoría de comandos</summary><pre id="audit"></pre></details></main><script src="project-config.js"></script><script src="game.js"></script></body></html>'''
    put('index.html',game_html)
    put('project-config.js','window.GAMEB_PROJECT = '+json.dumps(proj,ensure_ascii=False,separators=(',',':'))+';')
    css='''*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#263e5c,#080d18 70%);color:#f4f7ff;font:16px system-ui,sans-serif;min-height:100vh;display:grid;place-items:center;padding:16px}main{width:min(980px,100%);background:#111b2d;border:1px solid #344864;border-radius:20px;padding:20px;box-shadow:0 20px 70px #0008}header{text-align:center}h1{color:#f4cf75;margin:0}.reels{display:grid;grid-template-columns:repeat(var(--cols,5),1fr);gap:8px;margin:20px auto;max-width:760px}.cell{aspect-ratio:1/1.05;background:linear-gradient(#263a56,#111b2c);border:2px solid #71809b;border-radius:12px;display:grid;place-items:center;font-size:clamp(24px,5vw,50px);overflow:hidden}.cell img{width:100%;height:100%;object-fit:contain}.stats,.controls{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}.stats div{background:#0b1423;padding:10px 18px;border-radius:10px}.stats b{display:block;color:#f4cf75}button{padding:12px 17px;border-radius:10px;border:1px solid #51698c;background:#20334e;color:#fff;font-weight:800;cursor:pointer}#spin{background:linear-gradient(#f8d77e,#c58b2c);color:#1b1b1b;min-width:150px}button:disabled{opacity:.5}#status{text-align:center;color:#aebbd1}details{margin-top:16px}pre{white-space:pre-wrap;overflow:auto}@media(max-width:600px){main{padding:12px}.reels{gap:4px}.cell{border-width:1px;border-radius:7px}.stats{font-size:13px}}'''
    put('style.css',css)
    # symbols are safe JSON data
    js=r'''(()=>{const cfg=window.GAMEB_PROJECT||{};const syms=cfg.symbols?.length?cfg.symbols:[{id:'jade',label:'Jade',type:'normal',pay3:2,pay4:5,pay5:10,weight:20},{id:'sun',label:'Sol',type:'normal',pay3:1,pay4:3,pay5:7,weight:25},{id:'scarab',label:'Escarabajo',type:'normal',pay3:3,pay4:8,pay5:20,weight:12},{id:'WILD',label:'Comodín',type:'wild',weight:3},{id:'SCATTER',label:'Dispersión',type:'scatter',weight:2}];let credits=10000,bet=10,win=0,busy=false,turbo=false;const $=id=>document.getElementById(id);$('title').textContent=cfg.name||'GAMEB Prototype';const rows=+cfg.rows||3,cols=+cfg.columns||5;document.querySelector('.reels').style.setProperty('--cols',cols);const fallback=['💎','☀️','🪲','👑','⭐','🌙','🔱','🪬'];function choose(){let list=syms.filter(s=>s.type!=='scatter'&&s.type!=='wild');return list[Math.floor(Math.random()*list.length)]||syms[0]}function cellSymbol(s){return s?.label||s?.id||fallback[0]}function draw(grid){const root=$('reels');root.innerHTML='';grid.forEach((s,i)=>{const d=document.createElement('div');d.className='cell';const img=`assets/extracted/${(cfg.components||[]).find(c=>c.type==='Símbolo'&&c.name===s.label)?.id||''}.png`;const im=document.createElement('img');im.src=img;im.alt=cellSymbol(s);im.onerror=()=>{im.remove();d.textContent=s?.face||fallback[i%fallback.length]};d.appendChild(im);root.appendChild(d)})}function randomGrid(){return Array.from({length:rows*cols},()=>choose())}function evaluateDemo(grid){let total=0;for(let r=0;r<rows;r++){let line=grid.slice(r*cols,(r+1)*cols);let first=line[0];let n=1;for(let i=1;i<line.length&&line[i]?.id===first?.id;i++)n++;if(n>=3){let p=n>=5?first.pay5:n===4?first.pay4:first.pay3;total+=Math.round((Number(p)||0)*bet)}}return total}async function spin(){if(busy||credits<bet)return;busy=true;$('spin').disabled=true;credits-=bet;win=0;update();const final=randomGrid();const duration=turbo?250:+cfg.motion?.duration||1800;const start=Date.now();while(Date.now()-start<duration){draw(randomGrid());await new Promise(r=>setTimeout(r,turbo?65:100))}draw(final);win=evaluateDemo(final);credits+=win;busy=false;$('spin').disabled=false;update();$('status').textContent=win?`Premio demo: $${(win/100).toFixed(2)}`:'Sin premio demo. Los pagos son ilustrativos.'}function update(){$('credits').textContent='$'+(credits/100).toFixed(2);$('bet').textContent='$'+(bet/100).toFixed(2);$('win').textContent='$'+(win/100).toFixed(2)}$('spin').onclick=spin;$('betDown').onclick=()=>{bet=Math.max(10,bet-10);update()};$('betUp').onclick=()=>{bet+=10;update()};$('turbo').onclick=()=>{turbo=!turbo;$('turbo').textContent='TURBO: '+(turbo?'ON':'OFF')};draw(randomGrid());update();const handlers={spin:()=>spin(),betUp:()=>{bet+=10;update()},betDown:()=>{bet=Math.max(10,bet-10);update()},turbo:()=>{turbo=!turbo;update()},update:()=>update()};const test=[];for(const [name,fn] of Object.entries(handlers)){try{if(typeof fn!=='function')throw Error('no es función');test.push(name+': OK')}catch(e){test.push(name+': ERROR '+e.message)}}$('audit').textContent=test.join('\n')+'\nNOTA: esta auditoría confirma presencia y llamada de manejadores; no certifica el comportamiento visual ni matemática real.';})();'''
    put('game.js',js)
    # Copy base motor source for next-stage real integration, without implying game uses it yet
    for rel in ['game-config.js','reel-engine.js','demo-game.js','style.css','CONTRATO_MOTOR.md','CHECKLIST_NUEVO_JUEGO.md']:
     src=ROOT/'referencias'/'motor-base'/'BASE_MAESTRA_TRAGAMONEDAS_CONFIGURABLE'/rel
     if src.exists(): put('motor-base/'+rel,src.read_bytes())
    qa={'packageCreated':True,'componentsReceived':len(components),'cropsCreated':crop_count,'symbolsReceived':len(symbol_list),'checks':[{'name':'project.json exists','status':'PASS'},{'name':'manifest.json exists','status':'PASS'},{'name':'prototype files generated','status':'PASS'},{'name':'component crops generated','status':'PASS' if crop_count else 'WARN'},{'name':'mathematics certified','status':'NOT_RUN - demo only'},{'name':'browser visual test','status':'NOT_RUN'}],'important':'The starter prototype is not certified production math. Review generated crops and test in browser.'}
    put('REPORTE_QA.md','# Reporte QA\n\n'+json.dumps(qa,ensure_ascii=False,indent=2)+'\n')
    put('README.md',f'''# {name} · Proyecto inicial GAMEB\n\n1. Extrae este ZIP.\n2. Abre `index.html` en Chrome/Edge.\n3. Prueba GIRAR, apuesta y turbo.\n4. Revisa `REPORTE_QA.md` y `manifest.json`.\n\n## Contenido\n- `project.json`: especificación original del proyecto.\n- `manifest.json`: componentes, coordenadas, símbolos y movimiento.\n- `assets/extracted/`: recortes de las regiones detectadas. Los recortes de una captura pueden incluir píxeles vecinos; inspección manual requerida.\n- `motor-base/`: archivos fuente de referencia para integrar el motor configurable.\n\n## Limitaciones\nEste prototipo utiliza resultados aleatorios y evaluación de premios ilustrativa. No implementa ni valida el RTP real, reglas de bonus, todas las líneas, wild/scatter o certificación. La animación del prototipo es una vista inicial y no garantiza que todos los perfiles de movimiento estén conectados.\n''')
    z.close();blob=mem.getvalue();self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Disposition',f'attachment; filename="{name}_proyecto.zip"');self.send_header('Content-Length',str(len(blob)));self.end_headers();self.wfile.write(blob);return
   self.send_json(404,{'error':'Ruta no encontrada'})
  except Exception as e: self.send_json(500,{'error':str(e)})
 def do_GET(self):
  if self.path.startswith('/auth/callback'):
   try:
    query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
    creds=finish_oauth(query)
    html='<!doctype html><meta charset=utf-8><title>GAMEB Studio</title><body style="font:16px system-ui;background:#101827;color:#fff;padding:40px"><h2>ChatGPT conectado a GAMEB Studio</h2><p>Ya puedes cerrar esta pestaña y volver al panel GAMEB.</p><script>setTimeout(()=>window.close(),1200)</script></body>'
    b=html.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
   except Exception as e:
    b=('<!doctype html><meta charset=utf-8><body style="font:16px system-ui;background:#101827;color:#fff;padding:40px"><h2>No se pudo conectar ChatGPT</h2><pre>'+str(e).replace('&','&amp;').replace('<','&lt;')+'</pre><p>Regresa a GAMEB Studio e inténtalo de nuevo.</p></body>').encode();self.send_response(400);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
   return
  if self.path=='/api/auth/status':
   c=read_credentials();valid=bool(c.get('access_token') and 'chatgpt.tokens.use.direct' in c.get('scopes',[]))
   return self.send_json(200,{'ok':True,'connected':valid,'email':c.get('email',''),'name':c.get('name',''),'scopes':c.get('scopes',[]),'apiKeyConfigured':bool(os.environ.get('OPENAI_API_KEY')),'pillowAvailable':bool(Image)})
  if self.path=='/api/assets':
   assets=[]
   for f in sorted(ASSET_DIR.iterdir(),key=lambda x:x.stat().st_mtime,reverse=True):
    if f.is_file() and f.suffix.lower() in ('.png','.jpg','.webp'):
     mime={'.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp'}[f.suffix.lower()]
     assets.append({'name':re.sub(r'_\d{8}_\d{6}_\d+\.(?:png|jpg|webp)$','',f.name),'filename':f.name,'url':'/assets/imported/'+urllib.parse.quote(f.name),'bytes':f.stat().st_size,'type':mime})
   return self.send_json(200,{'ok':True,'assets':assets})
  if self.path=='/health': return self.send_json(200,{'ok':True,'chatgptConnected':bool(read_credentials().get('access_token')),'apiKeyConfigured':bool(os.environ.get('OPENAI_API_KEY')),'pillowAvailable':bool(Image),'assetCount':sum(1 for f in ASSET_DIR.iterdir() if f.is_file())})
  return super().do_GET()

def main():
 port=int(os.environ.get('GAMEB_PORT','8766'));print(f'GAMEB Studio Núcleo IA V2: http://127.0.0.1:{port}');print('Conexión ChatGPT:', 'credenciales guardadas' if read_credentials().get('access_token') else 'pendiente de iniciar sesión');print('API key de respaldo:', 'configurada' if os.environ.get('OPENAI_API_KEY') else 'no configurada');ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
if __name__=='__main__': main()
