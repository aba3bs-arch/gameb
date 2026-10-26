# Cursor dentro de GAMEB

El chat web usa la API oficial de Cursor Cloud Agents v1 mediante una función de Netlify. El botón «Conectar con Cursor» comprueba la configuración: no inicia una sesión de ChatGPT ni pide una contraseña de Cursor.

## Configuración

1. Crea una clave en https://cursor.com/dashboard con acceso a Cloud Agents.
2. En Netlify, abre la configuración del proyecto y añade `CURSOR_API_KEY` como variable de entorno secreta con alcance **Functions** para el contexto de despliegue correspondiente.
3. Vuelve a desplegar el sitio y pulsa «Conectar con Cursor».
4. Envía una orden. La primera orden comprueba el acceso real a la API; tener una clave configurada no garantiza permisos o saldo disponible.

La clave permanece en el servidor y no debe guardarse en el repositorio ni en el navegador. El uso está sujeto a los permisos, límites y facturación de Cursor. Configura límites de gasto en Cursor antes de compartir el sitio: quienes puedan acceder a este chat pueden enviar órdenes a la cuenta configurada.

Las conversaciones usan agentes sin repositorio y el modelo predeterminado de la cuenta. Cursor conserva el contexto del agente; una cookie firmada y HttpOnly identifica la conversación durante un día. GAMEB consulta el resultado cada tres segundos. «Detener» cancela la tarea en Cursor; «Limpiar conversación» inicia una conversación nueva. No se conectó un repositorio ni se habilitó la creación automática de cambios o solicitudes de integración.

La biblioteca de imágenes y el desarmador mantienen sus dependencias previas del servidor Python. Esta integración cubre el chat principal, sin prometer generación de imágenes PNG ni migrar esas funciones.

Documentación: https://cursor.com/docs/cloud-agent/api/overview

Validación local sin consumir la API: `node --experimental-strip-types --test tests/cursor.test.mjs`.
