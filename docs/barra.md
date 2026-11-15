# La barra de agentes

El requisito obligatorio: **ver los workspaces y, cuando hay sesiones de IA, a qué proyecto
pertenece cada una y qué está haciendo, sin liarte entre sesiones.**

## Qué ves
```
 ◖ 󰣇  ryce-pc — Montar el rice › Generar el fondo ◗   ◖ 1 󰖟 github.com  2 󱜙 ryce-pc · Montar el rice…  ⟨3 󱜙 brujula · Arreglar el log…⟩  4 󱜙 web-de-ejemplo  五  六 ◗   ◖ 󱜙 1   󰕾   󰈀   12:43 ◗
```
- **Isla izquierda**: la ventana activa. Si es Claude: `proyecto › lo que hace ahora`.
- **Isla central**: un hueco por workspace. Los cinco primeros están siempre; del 6 al 11
  aparecen cuando tienen algo. Número (el de tu atajo **Ctrl+N**), icono, **proyecto** y, si
  cabe, **tema** de la sesión. Los vacíos son numerales tenues.
- **Píldora blanca**: el workspace donde estás.
- **Anillo magenta** (`⟨3 …⟩` en el dibujo): esa sesión espera un permiso o una respuesta tuya.
- **Al pasar el ratón** por un hueco: proyecto, tema, las viñetas «Ahora…» y el estado.
- **Isla derecha**: cuántos agentes te esperan (o trabajan), volumen, red y hora. Si haces clic
  en el contador, se abre el panel lateral (también con **Super+A**).

Y fuera de la barra, **el borde de la ventana de la sesión que espera brilla en magenta**.

## De dónde sale cada dato
`agentd` es un servicio pequeño (Python, solo librería estándar, menos de 40 MB). Lo cruza
todo y escribe ficheros que la barra y el panel solo leen:

| Dato | Fuente |
|---|---|
| Qué ventana hay en cada workspace | Socket de eventos de Hyprland |
| Qué sesión de Claude corre en cada terminal | `/proc`: terminal → shell → proceso en primer plano |
| Estado (trabajando / te espera / en reposo) | `~/.claude/sessions/<pid>.json` |
| Proyecto | La raíz git del directorio de la sesión |
| Tema | El título que Claude genera para la sesión (`ai-title` del transcript) |
| Qué hace ahora | Tu convención **Ahora:** del chat → la última herramienta → el resumen de ausencia |
| Qué hizo (en reposo) | El bloque **Hecho:** del último turno |

**Privacidad**: nunca lee tus prompts (`last-prompt`, `history.jsonl`). Solo escribe a la
consola si la estás mirando, para no dejar títulos de proyectos en el registro del sistema.

## Por qué está hecho así
- **Waybar es la barra; el panel lateral (Quickshell) es aparte.** Si una actualización rompe
  Quickshell, la barra, que es lo obligatorio, sigue funcionando.
- **Un hueco por workspace** (`custom/wsN`) para que cada uno sea clicable.
- **Etiquetas de ancho fijo**: cambiar de workspace solo cambia colores, nada se desplaza.
- **Si agentd se para o se cae**, al salir limpia lo suyo: la barra vuelve a los números y
  ninguna ventana se queda marcada en magenta.
- **Servicios de systemd con reinicio automático**: la barra se cayó una vez en el portátil y
  nadie la relanzó durante horas.
- **El magenta lo pinta la hoja de estilos**: en el texto de la barra solo van grises.
- **Clic = `hyprctl dispatch 'hl.dsp.focus({ workspace = N })'`**: desde la 0.57, Hyprland
  solo entiende órdenes en Lua.

## Si algo no cuadra
| Síntoma | Mira |
|---|---|
| Huecos sin nombres, solo números | `systemctl --user status agentd` |
| Barra ausente | `systemctl --user status waybar` |
| Una sesión no aparece | Una sesión sin ningún mensaje todavía no existe en disco: escríbele algo |
| Una sesión dentro de tmux no marca su hueco | tmux esconde de qué ventana es la sesión: usa una ventana de kitty por sesión (**Ctrl + Enter**) |
| agentd parado o caído | La barra vuelve a los números solos (lo limpia al salir) y ninguna ventana se queda en magenta |
| No sale el brillo magenta, pero el anillo sí | Prueba: `bash install/verify.sh` (paso del brillo) |
