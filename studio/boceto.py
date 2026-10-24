"""Boceto SVG opcional. No sustituye al desarmador de PNG."""
import os, re
from studio.auth import access_token
from studio.openai_client import choose_model, openai_response

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
