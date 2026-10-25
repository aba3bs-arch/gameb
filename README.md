# GAMEB Studio Automatizado V2 · Conexión con ChatGPT

## Iniciar en Windows
1. Extrae el ZIP completo en una carpeta normal (no lo ejecutes dentro del ZIP).
2. Ejecuta `INICIAR_GAMEB_STUDIO.bat`. La primera vez puede instalar PyJWT/cryptography para validar de forma segura la identidad OAuth.
3. Abre `http://127.0.0.1:8765` si no se abre automáticamente.
4. Ve a la etapa **4 · IA y componentes** y pulsa **Conectar con ChatGPT**.
5. En el navegador inicia sesión y revisa los permisos. Para usar consumo elegible de tu plan debe concederse `chatgpt.tokens.use.direct` si está disponible para tu cuenta.
6. Cuando aparezca la página de conexión correcta, cierra esa pestaña y vuelve a GAMEB Studio. Sube el boceto y pulsa **Analizar boceto con IA**.

## Qué hace esta integración
- Implementa el flujo oficial Sign in with ChatGPT para aplicaciones locales de código abierto: OAuth con PKCE, `state`/`nonce`, callback de loopback, intercambio del código y validación de ID token con las claves públicas de OpenAI.
- Solicita el permiso opcional de uso del plan ChatGPT y envía solicitudes de Responses API con el token OAuth, `store:false` y `stream:true`.
- Guarda las credenciales localmente en `%LOCALAPPDATA%\GAMEBStudio\chatgpt_credentials.json`, fuera de la carpeta pública del servidor. No solicita ni guarda tu contraseña de ChatGPT.
- El botón **Desconectar** elimina el archivo local de credenciales.
- Si el usuario no autoriza el uso del plan o no es elegible, la función de IA no debe considerarse conectada. La plantilla manual continúa disponible.

## Requisitos y límites
- La conexión no da acceso a conversaciones ni memoria de ChatGPT.
- La disponibilidad del uso del plan depende de elegibilidad, autorización, límites y compatibilidad del servicio. No se puede garantizar el uso ilimitado ni que todos los planes/cuentas tengan el permiso.
- GAMEB es una app local personal. No se debe convertir este mecanismo en un proxy compartido ni utilizar la cuenta para solicitudes de otras personas.
- La integración de OAuth se implementó siguiendo la documentación pública actual, pero necesita una prueba real de autorización con tu cuenta. Este entorno no puede completar el inicio de sesión en tu navegador ni confirmar la elegibilidad de tu cuenta.
- La detección de componentes es una propuesta que requiere inspección manual. El ZIP de juego que se exporta sigue siendo un prototipo de demostración; no certifica RTP ni matemáticas comerciales.

## Documentación oficial
- https://developers.openai.com/siwc/token-sharing-open-source
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference

## Modo alternativo
Si decides usar API tradicional, GAMEB conserva soporte opcional para `OPENAI_API_KEY`; su facturación es separada de ChatGPT. No necesitas configurar esa variable para probar primero el inicio de sesión con ChatGPT.


## V4: generar boceto a partir de una idea

En la etapa **03 · Boceto** ahora puedes escribir una idea y pulsar **Generar boceto con IA**. El servidor solicita un diseño vectorial SVG al modelo disponible en la sesión autorizada de ChatGPT (o a la API si está configurada). Puedes descargar el SVG y convertirlo a PNG como referencia para la etapa 04.

Notas:
- Esta función genera un boceto vectorial de interfaz, no una imagen rasterizada fotorrealista ni arte final.
- El resultado de IA puede contener errores visuales; revisa y corrige el boceto.
- La conexión ChatGPT debe permitir solicitudes al modelo y el uso puede tener límites.
- La función se ha preparado en el código; el primer uso real depende de la autorización, disponibilidad del modelo y respuesta del servicio.


## V5: diagnóstico de generación bloqueada

Si el botón permanece en "La IA está diseñando..." la solicitud no ha terminado. Esta versión añade un límite de 45 segundos al servidor y 50 segundos en la interfaz para que el botón no quede girando indefinidamente, y muestra un error más claro. Mantén abierta la ventana negra de INICIAR_GAMEB_STUDIO.bat y revisa el mensaje que devuelve la interfaz.


## V6: corrección del filtro SVG

Se corrigió un falso positivo en el validador de SVG: la URL estándar `http://www.w3.org/2000/svg` del atributo `xmlns` ya no bloquea un SVG válido. Se siguen bloqueando scripts, eventos embebidos, imágenes/iframes y referencias externas peligrosas.


## V7: optimización del tiempo de generación

Se eliminó la consulta de catálogo `/v1/models` antes de cada generación. En V6 esa llamada podía tardar hasta 30 segundos y después se hacía una segunda solicitud de generación, provocando que la interfaz agotara sus 50 segundos de espera. Ahora se usa el modelo configurado directamente y, si no está disponible, se muestra el error HTTP real. Se aumentó el límite de generación a 60 segundos en el servidor y 65 segundos en el navegador, con límite de salida de 5000 tokens.


## V2: generación y vista previa de imágenes PNG

Se añadió un panel **Generador de imágenes reales** conectado a `POST /api/generate-image`. La ruta usa la herramienta `image_generation` de Responses API, valida que la respuesta contenga un PNG y devuelve el archivo en base64 para mostrarlo dentro del panel. Desde ahí se puede guardar el PNG. Si el servicio falla, la interfaz muestra el error recibido; no dibuja una imagen falsa de respaldo.

La generación necesita una sesión autorizada que permita usar la herramienta de imágenes o una variable `OPENAI_API_KEY` válida. El uso de la API tradicional puede generar cargos separados. El generador de bocetos SVG anterior se conserva por separado.


## Reestructura visual (2026-10-16)

- El chat IA se conserva como módulo independiente.
- La biblioteca visual permite importar PNG, JPG y WebP, previsualizar, descargar y eliminar assets.
- Los archivos importados se guardan localmente en `assets/imported/`.
- La generación directa de imágenes mediante la sesión compartida de ChatGPT se deshabilitó porque el servicio rechaza esa capacidad; no se simula una generación. Los bocetos se diseñan en ChatGPT y después se importan.
