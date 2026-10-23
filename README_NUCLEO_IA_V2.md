# GAMEB Studio — Núcleo IA V2 (generación visual)

## Objetivo
Esta versión es una reconstrucción de la entrada principal como un espacio de trabajo de comandos. Conserva el módulo OAuth existente como base y añade un endpoint de chat en streaming para que los fragmentos de respuesta se muestren mientras llegan.

## Instalar y abrir en Windows
1. Extrae el ZIP completo en una carpeta nueva.
2. Ejecuta `INICIAR_GAMEB_STUDIO.bat`.
3. Se abrirá `http://127.0.0.1:8766`.
4. Pulsa **Conectar con ChatGPT** si el estado dice que no estás conectado. Completa la autorización y vuelve al panel.
5. Escribe una orden en el chat y pulsa **Enviar orden**. Los fragmentos de texto deben aparecer progresivamente.

## Qué incluye
- Pantalla principal nueva de comandos en lugar del flujo de siete etapas.
- Estado de conexión y botones de conectar/desconectar.
- Endpoint `/api/assistant-stream` que reenvía eventos de texto del flujo de Responses API como eventos SSE al navegador.
- Contexto local del proyecto: nombre, tema y tamaño de rodillos.
- Botón detener solicitud, historial de conversación limitado a 12 mensajes y mensajes de error visibles.
- Se conservan los motores y herramientas anteriores en `referencias/` para migrarlos en fases posteriores.

## Limitaciones importantes
- El panel de generación de imágenes PNG reales ya está conectado. El editor de componentes y el motor de juego siguen siendo módulos separados y no se deben considerar terminados.
- La conexión OAuth y el permiso de uso del plan dependen de la elegibilidad de la cuenta y del servicio.
- No se pudo probar una solicitud real con la cuenta del usuario desde este entorno. Se verificó sintaxis e integridad del paquete; la prueba de extremo a extremo debe hacerse en su Windows.
- Si aparece error, conserva la ventana negra del servidor y comparte el texto exacto.
- No compartas contraseña ni tokens de autorización.


## Corrección de modelo

La selección de modelo ahora consulta `/v1/models` con el token de la sesión y elige un modelo con `visibility=list`, conservando el orden devuelto por el servicio. La lista se almacena en memoria durante 10 minutos para no retrasar cada orden. Se eliminaron `max_output_tokens` de las solicitudes de uso del plan ChatGPT porque no está admitido en el modo preview de Sign in with ChatGPT. La selección y la generación de boceto usan el mismo mecanismo.


## Reestructura visual (2026-10-16)

- El chat IA se conserva como módulo independiente.
- La biblioteca visual permite importar PNG, JPG y WebP, previsualizar, descargar y eliminar assets.
- Los archivos importados se guardan localmente en `assets/imported/`.
- La generación directa de imágenes mediante la sesión compartida de ChatGPT se deshabilitó porque el servicio rechaza esa capacidad; no se simula una generación. Los bocetos se diseñan en ChatGPT y después se importan.


## Desarmador visual
Abre `desarmador.html` desde el navegador o desde el enlace de la página principal. Permite cargar una referencia, crear recortes por cuadrícula o mediante selección manual, moverlos, asignar nombre/tipo y guardar uno o todos los recortes PNG en `assets/imported/`. Las cuadrículas son propuestas geométricas, no detección semántica automática; revisa cada recorte antes de usarlo.
