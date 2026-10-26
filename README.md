# gameb
juegos en linea

## Publicación en Netlify

`netlify.toml` configura la publicación de las páginas de `web/` y las imágenes
de `assets/` en `dist/`. La página principal queda disponible en `/` y el
desarmador en `/desarmador.html`. Las direcciones anteriores bajo `/web/`
redirigen a las nuevas rutas.

La publicación estática permite abrir la interfaz. Las rutas `/api/` del
servidor Python siguen requiriendo la instalación local; todavía no están
implementadas como funciones de Netlify.
