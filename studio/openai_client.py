"""Llamadas a la Responses API. No elige cajas de título."""
import json, urllib.request, urllib.error, socket

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
