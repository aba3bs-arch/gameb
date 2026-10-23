"""Sign in with ChatGPT. Las credenciales quedan fuera de la carpeta pública."""
import os, json, base64, urllib.request, urllib.error, urllib.parse, time, secrets, hashlib, threading, uuid, datetime
from studio.paths import APPDATA, CREDENTIALS_FILE, HOST_FILE

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
