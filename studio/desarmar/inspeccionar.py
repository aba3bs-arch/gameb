"""Compara el PNG con el boceto. Una palabra alta que falta bloquea el registro automático."""
from studio.auth import access_token
from studio.datos import decode_data
from studio.desarmar.unir import TITLE_LAWS, _is_title_kind
from studio.openai_client import choose_model, openai_response
import json
import os


def listo_para_registrar(ready, issues):
    """Un defecto de severidad Alta impide dar de alta el título sin revisión."""
    if any(isinstance(item, dict) and item.get('severity') == 'Alta' for item in issues or []):
        return False
    return bool(ready)


def inspect_crop_with_openai(image_data, name, category, notes, original_image='', words=None):
    token = access_token()
    auth_mode = 'chatgpt'
    if not token:
        token = os.environ.get('OPENAI_API_KEY', '').strip()
        auth_mode = 'api'
        if not token:
            raise RuntimeError('La inspección IA necesita una sesión de ChatGPT compatible o OPENAI_API_KEY configurada en el servidor. El recorte no se envió ni se modificó.')
    head, raw = decode_data(image_data)
    mime = head.split(':', 1)[1].split(';', 1)[0] if head.startswith('data:') else 'image/png'
    title_check = _is_title_kind(category) or _is_title_kind(name)
    original_ok = bool(original_image) and isinstance(original_image, str) and original_image.startswith('data:image')
    listed = [str(word)[:40] for word in (words or []) if str(word).strip()][:8]
    word_rule = ''
    if title_check and listed:
        word_rule = ' El recorte tiene que mostrar estas palabras: ' + ', '.join(listed) + '. Si falta cualquiera, añade un problema de severidad Alta y ready_to_register false.'
    prompt = f'''Eres un inspector visual de componentes gráficos para videojuegos. Nombre: {name or 'Componente sin nombre'}. Categoría declarada: {category or 'Sin categoría'}. Instrucciones del usuario: {notes or 'Revisión general de calidad visual'}.
{TITLE_LAWS if title_check else ''}
{'La primera imagen es el boceto completo y la segunda es el recorte del título. Compara las dos. Si en el boceto el letrero tiene una palabra o un adorno que no está en el recorte, es un defecto de severidad Alta y ready_to_register debe ser false.' if title_check and original_ok else 'Examina el recorte adjunto, no imagines detalles que no se ven.'}{word_rule}
Busca problemas que sí sean visibles: bordes cortados, restos de fondo, halos, manchas, transparencias accidentales, deformación, desenfoque, baja resolución, márgenes desiguales, partes faltantes, texto/números residuales o elementos ajenos. Distingue defectos confirmados de posibles riesgos. Si el fondo cuadriculado/transparente no puede deducirse con certeza de la imagen, dilo. No cambies ni reconstruyas la imagen. Devuelve SOLO JSON válido con esta forma exacta: {{"summary":"resumen en español","quality":"Correcto|Revisar|Defectos detectados","issues":[{{"severity":"Alta|Media|Baja|Observación","title":"problema breve","detail":"qué se ve y dónde","recommendation":"acción concreta sin alterar el diseño original"}}],"strengths":["aspecto que está bien"],"ready_to_register":false,"confidence":0.0}}. Incluye máximo 8 problemas, evita falsos positivos y usa lista vacía si no encuentras problemas claros. ready_to_register debe ser true solo si no hay defectos relevantes visibles; la decisión final siempre pertenece al usuario.'''
    content = [{'type': 'input_text', 'text': prompt}]
    if title_check and original_ok:
        content.append({'type': 'input_image', 'image_url': original_image, 'detail': 'high'})
    content.append({'type': 'input_image', 'image_url': image_data, 'detail': 'high'})
    model = choose_model(token)
    body = {'model': model, 'input': [{'role': 'user', 'content': content}], 'text': {'format': {'type': 'json_object'}}}
    parsed = json.loads(openai_response(body, token))
    issues = parsed.get('issues', [])
    if not isinstance(issues, list):
        issues = []
    clean = []
    for item in issues[:8]:
        if not isinstance(item, dict):
            continue
        severity = item.get('severity', 'Observación')
        if severity not in ['Alta', 'Media', 'Baja', 'Observación']:
            severity = 'Observación'
        clean.append({
            'severity': severity,
            'title': str(item.get('title', 'Detalle visual'))[:120],
            'detail': str(item.get('detail', ''))[:600],
            'recommendation': str(item.get('recommendation', ''))[:600],
        })
    strengths = parsed.get('strengths', [])
    if not isinstance(strengths, list):
        strengths = []
    quality = parsed.get('quality') if parsed.get('quality') in ['Correcto', 'Revisar', 'Defectos detectados'] else ('Defectos detectados' if clean else 'Revisar')
    try:
        confidence = max(0, min(1, float(parsed.get('confidence', .5))))
    except (TypeError, ValueError):
        confidence = .5
    return {
        'ok': True,
        'summary': str(parsed.get('summary', 'Inspección terminada.'))[:1200],
        'quality': quality,
        'issues': clean,
        'strengths': [str(item)[:300] for item in strengths[:6]],
        'ready_to_register': listo_para_registrar(parsed.get('ready_to_register', False), clean),
        'confidence': confidence,
        'model': model,
        'authMode': auth_mode,
        'imageBytes': len(raw),
        'mimeType': mime,
    }


def revisar(data):
    original = str(data.get('original') or '')
    if len(original) > 8_000_000:
        original = ''
    words = data.get('words') if isinstance(data.get('words'), list) else []
    try:
        result = inspect_crop_with_openai(
            str(data.get('image', '')),
            str(data.get('name', ''))[:120],
            str(data.get('category', ''))[:80],
            str(data.get('notes', ''))[:1200],
            original,
            words,
        )
        return 200, result
    except Exception as exc:
        return 502, {'ok': False, 'error': str(exc)}
