# CHANGELOG · GAMEB Studio Núcleo IA V2

- Se corrigió la identificación visible de versión: el proyecto pasa de la etiqueta interna V1 a V2.
- Se añadió un panel visible para generación de imágenes PNG reales mediante la herramienta `image_generation` de Responses API.
- Se conectó la generación a una ruta de servidor dedicada y se valida el resultado PNG antes de mostrarlo.
- Se añadió vista previa, estado de generación, selección de formato/calidad y enlace para guardar el PNG.
- Se conservó el chat IA, el inicio/cierre de sesión, el guardado del contexto local, la ruta de bocetos SVG, el análisis de referencia y la exportación ZIP.
- No se declara probado el servicio remoto sin credenciales reales; se incluyen pruebas locales estáticas y de sintaxis.

## Corrección adicional: órdenes visuales desde el chat
- El chat detecta solicitudes de imágenes/bocetos y las envía directamente al endpoint de generación PNG en vez de pedirle al asistente textual una descripción.
- Cuando termina, inserta la imagen rasterizada y un enlace para guardar en el propio chat.
- Si la generación falla, el error queda visible tanto en el chat como en el panel del generador.
- Se conservan las órdenes no visuales en el flujo normal del asistente.


Reconstruccion del modulo visual: el endpoint de generacion ahora consume el flujo SSE requerido por Responses API (stream=true), captura errores del stream y extrae el resultado PNG de la respuesta completada.


## 2026-10-16 — Reestructura de flujo visual
- Retirado el botón de generación que fallaba por capacidades no soportadas en sesión compartida.
- Añadida biblioteca local de assets: importar, listar, previsualizar, descargar y eliminar PNG/JPG/WebP.
- Las órdenes de imagen en el chat explican el flujo real de trabajo en vez de llamar a un endpoint incompatible.
- El chat, OAuth, contexto de proyecto, análisis de referencias y exportador ZIP permanecen separados.

- Añadido módulo Desarmador visual con recortes por cuadrícula y selección manual sobre la imagen original.
- Guardado individual o masivo de componentes PNG en la Biblioteca visual.

## 2026-10-16 — Inspección inteligente de recortes
- Añadido el botón **Analizar recorte con IA** dentro de la inspección ampliada de cada componente.
- La inspección analiza únicamente el PNG recortado y devuelve resumen, nivel de revisión, problemas visibles, recomendaciones y aspectos correctos.
- Añadido campo opcional para pedirle a la IA que revise puntos concretos (por ejemplo, bordes, restos de fondo o partes cortadas).
- La IA no edita ni registra automáticamente el recorte; el usuario conserva la decisión final y el botón **Dar de alta** existente.
- Se muestra un mensaje claro si no hay una conexión de IA compatible o falla el servicio. La función remota requiere sesión compatible o `OPENAI_API_KEY` configurada en el servidor.
- Validaciones locales: compilación Python, sintaxis JavaScript y prueba simulada del analizador. La llamada remota real y la interacción visual completa quedan pendientes de validar en el equipo del usuario.

## Ajuste de separación de componentes cercanos (2026-10-16)
- La instrucción de análisis visual ahora exige una caja independiente por componente cuando dos objetos se tocan o están muy próximos.
- Las cajas deben cubrir el componente completo, incluidas puntas, sombras y adornos, con un margen pequeño cuando exista espacio; no deben fusionar objetos distintos.
- El análisis ordena las piezas de primer plano antes de procesarlas y deja la escena de fondo al final.
- Se conserva la deduplicación únicamente para cajas prácticamente idénticas; el solapamiento normal entre componentes cercanos no es motivo para fusionarlos.
- Validación local: `server.py` compila y el JavaScript inline pasa `node --check`. La segmentación real con rembg/IA requiere probarse en el equipo del usuario con una imagen real y sus dependencias.


## 2026-10-16 — Validación de cajas completas
- Se reforzaron las instrucciones de visión para delimitar títulos/logos como letreros completos, no solo el texto central.
- Se amplían las regiones de análisis de títulos y jackpots con márgenes específicos, conservando cada componente por separado y dentro de la imagen original.
- La caja inicial se considera provisional; no se afirma que la máscara haya sido validada visualmente solo por haber identificado el objeto.


## Revisión de calidad visual (2026-10-16)
- El índice técnico ya no puede mostrar 100/100: mide transparencia y condiciones de borde, pero no demuestra que la IA haya conservado todos los adornos del componente.
- La evaluación siempre solicita revisión visual y advierte revisar límites, partes cortadas y contaminación de objetos vecinos.
- La detección semántica y la máscara alfa se consideran etapas distintas; encontrar una pieza no equivale a validar su silueta completa.

## Revisión de calidad visual y robustez del desarmador (2026-10-16)
- Se aumentó el margen provisional de análisis para títulos/logotipos ornamentados (15% horizontal y 18% vertical), manteniendo cada componente como pieza independiente.
- Se reforzó el texto de análisis para aclarar que la caja inicial es provisional y que los cuatro extremos y adornos deben revisarse antes de aceptar la silueta.
- La vista previa usa dimensiones de respaldo si el contenedor todavía no reporta tamaño, evitando crear un visor de tamaño cero durante la apertura.
- La selección de componentes valida índices y actualiza la inspección abierta cuando corresponde.
- El guardado masivo omite piezas de primer plano que no tienen una silueta procesada válida; las escenas de fondo se conservan como recortes originales.
- El índice de calidad se describe explícitamente como señales técnicas de riesgo, nunca como garantía de integridad semántica.
- Validación realizada: compilación Python y comprobación de sintaxis JavaScript cuando Node.js está disponible. La calidad visual final requiere probar con la imagen original en Windows.
