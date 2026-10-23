# Protocolo de prueba rigurosa — Desarmador visual

## Objetivo
Validar la extracción de componentes del boceto antes de considerar fiable el flujo automático. Esta guía no afirma que la IA tenga una precisión perfecta: obliga a detectar y registrar los fallos.

## Corrección incluida en esta versión
- Se corrigió una regla CSS que ocultaba permanentemente `.inspectModal` (`display:none!important`). La ventana ahora se abre al pulsar **Inspeccionar** y se cierra con su botón, Escape o clic fuera de la ventana.
- Se conserva el módulo existente y sus herramientas automáticas; no se rehízo el resto de GAMEB Studio.

## Prueba piloto de cinco componentes
Usar la misma imagen maestra original para todos los casos:
1. Título/logotipo (bordes finos y letras).
2. Jackpot (marco ornamentado y números).
3. Símbolo compacto (por ejemplo, el sol).
4. Personaje o decoración con forma irregular (por ejemplo, cactus).
5. Fondo base (debe conservar el escenario; no aplicar rembg como si fuera un objeto de primer plano).

## Criterios por PNG
- El PNG abre y sus dimensiones coinciden con el recorte previsto.
- El objeto no pierde puntas, letras, ornamentos ni huecos interiores.
- El exterior del objeto es transparente para piezas de primer plano.
- No hay halo claro/oscuro apreciable sobre fondo claro, oscuro y tablero de transparencia.
- No hay restos visibles de otros componentes superpuestos.
- La pieza conserva sus coordenadas respecto a la imagen maestra.
- El fondo se evalúa aparte; no se considera limpio si conserva títulos o jackpots encima.

## Resultado esperado
Registrar para cada componente: nombre, dimensiones, tipo, si la máscara fue generada, alertas técnicas, inspección visual (aprobado / repetir) y motivo. Una puntuación técnica no sustituye la inspección visual. No aprobar automáticamente máscaras vacías ni piezas con errores.

## Cómo comprobar en Windows
1. Descomprime el ZIP en una carpeta nueva y conserva el proyecto anterior como respaldo.
2. Ejecuta `INICIAR_GAMEB_STUDIO.bat`.
3. Carga la imagen maestra y ejecuta la identificación automática.
4. En la lista de piezas pulsa **Inspeccionar**: la ventana debe abrirse sobre la aplicación y mostrar el recorte.
5. Prueba los fondos claro, oscuro y a cuadros. Cambia a la pieza siguiente y confirma que la vista cambia.
6. En primer plano, ejecuta quitar fondo y revisa el informe técnico. No aceptes el resultado únicamente por el porcentaje.
7. Exporta solo tras verificar cada pieza. Si el contorno está mal, anota el tipo de fallo para corregir el modelo o la máscara.

## Validaciones realizadas al preparar este ZIP
- Sintaxis del JavaScript incrustado en `desarmador.html` verificada con `node --check`.
- `server.py` compilado con `py_compile`.
- Integridad del ZIP comprobada tras empaquetar.
- No se ha ejecutado la aplicación en Windows ni se declara validada la precisión visual de las máscaras.
