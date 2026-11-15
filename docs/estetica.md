# Estética: «Marco», cinco temas

## La idea en una frase
La barra **flota**: no tiene fondo propio, cada grupo de la barra es una pieza suelta con su
sombra y el fondo de pantalla se ve alrededor (desde el 2026-11-12; antes era el borde grueso de
un marco). Del marco quedan solo las **esquinas redondeadas de la pantalla**. Los paneles
(Super+A), el selector de temas (Super+T) y los avisos siguen saliendo de los bordes, como
cajones. Encima de esa estructura hay **cinco temas**, y cada uno cambia todo a la vez:
colores, tipografía, forma, movimiento, fondo y hasta la pantalla de bloqueo.

## Por qué así
El rice anterior («Señal Magenta») quedaba de juguete: islas flotantes, mucho brillo y un
magenta que gritaba. Lo pedido ahora es lo contrario: sombrío, casi monocromo, con algo de
variedad en la paleta, muy fluido y uniforme en todas las aplicaciones.

De la inspiración (los cinco posts de r/unixporn) se cogió el método, no el
aspecto: rampas de grises con nombre y un único acento «vivo» (el post de Nothing OS), curvas
de movimiento que deceleran al entrar y aceleran al salir, muelles para las ventanas (el de la
Surface y el «as fluid as it gets»), dos acentos con significado (ctOS) y fondos desaturados
con estadísticas sobre el escritorio (el KDE monocromo). Ninguna configuración se ha copiado.

## Los cinco temas

| | **Origen** | **Grafito** | **Ola** | **Tinta** | **Papel** |
|---|---|---|---|---|---|
| Idea | Taller gruvbox: madera, crema y un naranja que solo avisa | Un instrumento: grises puros, números de puntos | La gran ola de Hokusai: tinta índigo y papel de arroz | Manga en blanco y negro, como el post r/unixporn 1tg82cr | Papel de lectura: las portadas del Ludwig Wittgenstein Project hechas escritorio; el único tema claro |
| Temperatura | cálida | neutra | fría | neutra | cálida |
| Letra de la interfaz | Martian Mono (la de la marca) | Space Grotesk | Inter | JetBrains Mono | Space Mono (la de las portadas) |
| Letra grande (reloj) | Martian Mono | Doto, de puntos (a 26 px o más) | Instrument Serif | JetBrains Mono | Space Mono Bold |
| Forma | fichas redondeadas (12–16 px) | casi recta (2–6 px) | cápsulas y squircles (16–22 px) | cajas con filo de 1 px, sin marco lateral | hoja casi recta (2–4 px), píldoras redondas como los puntos |
| Barra | fichas flotantes con iconos de colores | tres placas negras con separadores de punto, **todo en la letra de puntos del reloj** (Doto) | cápsulas flotantes, reloj con serifa | cajitas ahumadas flotantes, hora sobre fecha | tinta sobre papel; el workspace activo es un punto lleno |
| Color | colores gruvbox en barra, terminal y prompt | gris; la terminal sin azul | colores kanagawa | gris con un susurro de tono | tinta cálida y grises; la terminal en tintas oscuras legibles sobre crema |
| Movimiento | de cine, con un pequeño rebote al abrir | mecánico: corto y seco | fluido: muelles | seco, de terminal: fundidos cortos | pausado: una página que se asienta, sin rebote |
| Fondo | *Twilight in the Wilderness* (Church) | placa de puntos que dibuja la peonza (generada) | *La gran ola* | la lámina RY-PZ-002, el despiece de la peonza | el Tractatus, un punto por proposición, dibujando la peonza (generado) |
| Bloqueo y acceso | *Autumn – On the Hudson River* (Cropsey) | la placa de puntos | *Fuji rojo* | la peonza en semicorte, tan cerca que el borde se sale de la pantalla | una portada: el libro en puntos con una ventana donde va la hora |
| Escritorio | — | — | — | panel de datos estilo YoRHa, reloj binario de círculos y visualizador de puntos en el borde | reloj, datos y Hito en ventanas recortadas en los puntos |
| El acento («te espera») | naranja `#fe8019` | rojo `#e62d33` | rosa sakura `#d27e99` | ámbar `#ffb000` | lápiz rojo `#ad3a24` |

Los fondos son imágenes reales buscadas en internet (salvo Grafito y Papel, generados); de dónde sale cada una
y su licencia está en `assets/wallpapers/README.md`. La terminal y los editores usan siempre
JetBrainsMono Nerd Font: es letra de trabajo y no debe cambiar de ancho al cambiar de tema.

## La terminal y el prompt
Cada tema trae sus 16 colores de terminal, distintos de verdad entre temas, y con ellos los
colores de `ls`, `grep`, `fzf`, `git`/delta, `man`, `lsd`, yazi, btop, cava, Neovim y **Claude
Code** (un tema propio en `~/.claude/themes/ryce.json`, que se elige una vez en `/theme` como
«ryce»). Ningún directorio sale azul. El prompt no termina en `❯`: el último carácter es la
peonza, siempre de pie y un poco más grande (ocupa tres celdas, así nunca se recorta): en el
color del tema si el último comando fue bien, **roja** si falló y apagada en el modo normal de
vi. Todos los temas llevan **la raya de Tinta**: dos líneas unidas por una esquina (`╭─`/`╰─`,
en Tinta `┌─`/`└─`) y una raya hasta la hora. Lo de dentro cambia por tema: cápsulas de color
en Origen, línea de instrumento en Grafito, bandas inclinadas en Ola, corchetes en Tinta y una
cabecera de libro, con puntos medios, en Papel. En
cuanto un comando se ejecuta, su prompt se recoge en una sola línea (`hora <peonza> orden`):
el historial se lee como un registro y ninguna raya se rompe cuando la ventana cambia de
tamaño.

## El acento significa una sola cosa
Cada tema tiene un color de acento y **solo aparece cuando una sesión de IA te espera**: el
borde de su ventana, un punto en su hueco de la barra, la peonza de la barra cabeceando en
ese color y su tarjeta en el panel lateral. Sin halos ni brillos. Si no ves el acento en la
pantalla, nadie te necesita. Un linter (`tools/lint.py`) falla si el acento aparece en
cualquier otro sitio.

## La peonza
El logo de `logo-peonza` sustituye al de Arch en la esquina de la barra y **está viva**:
quieta cuando ninguna sesión trabaja, girando (el estado «pensando» de la marca) mientras
alguna trabaja, y cabeceando en el color del acento cuando una te espera. Es también un
carácter de la fuente propia «Ryce Peonza» (U+100000 en la barra; U+100003, de pie y de tres
celdas, en el prompt), y así sale en la terminal,
en la barra de respaldo y donde haga falta texto. Los fotogramas salen del mismo modelo de la
marca (`~/Repos/logo-peonza/src/pose.mjs`), no de una copia.

## Una sola fuente por tema
`contracts/themes/<tema>.json` es la única fuente de cada tema. De ahí salen, ya generados y
guardados en `themes/<tema>/`, la paleta de Hyprland, la de la barra de respaldo, la de
Quickshell, kitty, rofi, mako, fish, starship, fastfetch, btop, cava, Neovim, VS Code, GTK
(Thunar), Qt, la pantalla de bloqueo, el login, los fondos, los fotogramas de la peonza, el tema
de Claude Code y las pantallas de arranque. Un tema puede tener su propia versión de una
plantilla en `theme/templates/@<tema>/`, para cambiar la forma y no solo el color. Cambiar de tema es mover un solo enlace (`~/.local/state/ryce/theme/current`) y
avisar a cada programa: `ryce-theme set <tema>`, Super+Shift+T o el selector (Super+T).

## Reglas de legibilidad
- Texto con un contraste de al menos 4,5:1 y marcas de al menos 3:1 en los cinco temas; el
  generador se niega a escribir un tema que no lo cumpla.
- El acento, lejos de todos los grises (ΔE2000 ≥ 20) y distinguible de los colores de la
  terminal (ΔE2000 ≥ 12).
- Iconos solo de la familia Material Design de Nerd Fonts, la única con ancho uniforme.
- Nada de brillos permanentes ni de animaciones en bucle: la gráfica es integrada. Lo que se
  mueve, se mueve cuando algo cambia y luego se queda quieto.
