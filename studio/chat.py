"""Chat en streaming. No recorta piezas ni decide títulos."""
import os, json, urllib.request, urllib.error
from studio.auth import access_token
from studio.openai_client import choose_model

def transmitir(handler, data):
    token=access_token()
    mode='chatgpt'
    if not token:
     token=os.environ.get('OPENAI_API_KEY','').strip()
     mode='api'
    if not token: return handler.send_json(401,{'error':'No hay sesión ChatGPT activa ni API key configurada.'})
    messages=data.get('messages',[])
    if not isinstance(messages,list): return handler.send_json(400,{'error':'El historial debe ser una lista.'})
    clean=[]
    for m in messages[-12:]:
     if not isinstance(m,dict) or m.get('role') not in ('user','assistant'): continue
     content=str(m.get('content',''))[:5000]
     if content: clean.append({'role':m['role'],'content':content})
    if not clean or clean[-1]['role']!='user': return handler.send_json(400,{'error':'Escribe una orden antes de enviar.'})
    system_prompt=("Eres GAMEB Studio, asistente técnico en español para crear prototipos de tragamonedas de demostración. "
    "Trabaja como un copiloto: entiende órdenes, haz preguntas solo si faltan datos esenciales, resume acciones concretas. "
    "No afirmes que has editado archivos ni probado el juego si no se ejecutó una herramienta real. "
    "Distingue boceto visual, matemática de demostración y juego probado. La matemática y RTP deben validarse con simulaciones antes de considerarse fiables. "
    "Cuando el usuario pida diseñar, devuelve un plan claro y una especificación estructurada en texto; no inventes acceso a archivos.")
    body={'model':choose_model(token, use_chatgpt_plan=(mode=='chatgpt')),'instructions':system_prompt,'input':clean,'stream':True,'store':False}
    try:
     req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'text/event-stream'},method='POST')
     with urllib.request.urlopen(req,timeout=60) as upstream:
      handler.send_response(200);handler.send_header('Content-Type','text/event-stream; charset=utf-8');handler.send_header('Cache-Control','no-cache, no-transform');handler.send_header('Connection','close');handler.end_headers()
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
        handler.wfile.write(('data: '+packet+'\n\n').encode());handler.wfile.flush()
       elif typ in ('response.failed','error'):
        er=ev.get('response',{}).get('error') or ev.get('error') or {}
        msg=str(er.get('message') or er.get('code') or ev.get('message') or 'Error del modelo')
        packet=json.dumps({'type':'error','message':msg},ensure_ascii=False)
        handler.wfile.write(('data: '+packet+'\n\n').encode());handler.wfile.flush()
       elif typ=='response.completed':
        packet=json.dumps({'type':'done','mode':mode},ensure_ascii=False)
        handler.wfile.write(('data: '+packet+'\n\n').encode());handler.wfile.flush()
      return
    except urllib.error.HTTPError as e:
     bodyerr=e.read().decode(errors='replace')[:500]
     if 'subscription_sharing_usage_limit_exceeded' in bodyerr or 'subscription_sharing_usage_unavailable' in bodyerr: msg='El uso del plan ChatGPT no está disponible o llegó a su límite.'
     else: msg='Error HTTP '+str(e.code)+': '+bodyerr
     return handler.send_json(502,{'error':msg})
    except Exception as e:
     return handler.send_json(502,{'error':'No se pudo iniciar el flujo: '+str(e)})
