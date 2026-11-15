# Por qué Arch Linux (y no otra)

Decidido el 2026-11-09 tras investigar en paralelo con dos enfoques opuestos: «cuál es la
mejor» y «qué se rompe en 1–3 años». Los dos llegaron por separado a la misma respuesta.

## El veredicto
**Arch Linux**, instalada con su asistente oficial (archinstall 4.5) sobre btrfs, con
instantáneas (Snapper) que se arrancan desde el menú de GRUB, dos núcleos (`linux` y
`linux-lts`) y la familia de Hyprland fijada para que solo se actualice cuando tú decidas.

## Por qué gana
| Criterio (lo que pediste) | Arch |
|---|---|
| Hyprland obligatorio | Hyprland solo **garantiza** su funcionamiento en Arch y NixOS (wiki oficial). Arch empaqueta cada versión el mismo día que sale (0.57.1 el 2026-11-03) |
| Todo el rice sin terceros | Hyprland, Waybar 0.16, Quickshell 0.3.2, hyprlock, awww y matugen están en `extra`. **Cero AUR**: los 120 paquetes de este repo son oficiales |
| Hardware nuevo (Arrow Lake) | Núcleo 7.2 y Mesa 26.2: muy por encima del mínimo (núcleo 6.8, Mesa 24.1) |
| IA y desarrollo | El binario nativo de Claude Code, Docker, Node, Python con uv y Rust funcionan tal cual |
| Que no falle en el futuro | Instantáneas antes y después de cada actualización, núcleo LTS de reserva y Hyprland fijado |
| Fácil para ti | Ya lo usas: tus dotfiles, Torre y la barra salen de ahí |

## Por qué no las demás
- **CachyOS** (segunda opción): es Arch con núcleos, cargador de arranque y repositorios
  propios. Todos los hilos de 2026 sobre arranques rotos que encontramos estaban en esas
  capas extra, y su ganancia de rendimiento no se nota con tu tipo de trabajo.
- **openSUSE Tumbleweed** (tercera): la mejor recuperación de serie, pero supone cambiar de
  ecosistema (zypper, SELinux) y no está claro que tenga Quickshell.
- **Fedora**: retiró Hyprland de sus repositorios (2025-09-30, «fails to install») y el COPR
  de referencia está muerto desde 2025-10.
- **Ubuntu 26.04 LTS**: Hyprland congelado en 0.53.3 durante años, anterior a la configuración
  en Lua. Además AppArmor bloquea el sandbox de Claude Code hasta que se le añade un perfil.
- **NixOS**: la mejor vuelta atrás de todas, pero el binario nativo de Claude Code se rompe en
  cada autoactualización y la versión estable va por detrás con Hyprland.
- **Omarchy**: está hecho para controlar tus dotfiles. Sus actualizaciones han pisado atajos
  personalizados (issue #1802).
- **EndeavourOS**: es Arch con un instalador gráfico. No aporta nada a quien ya usa Arch.

## Los riesgos que quedan y cómo están cubiertos
1. **Hyprland cambia su configuración a menudo**: 7 versiones con cambios incompatibles en
   unos 20 meses. La 0.57 **eliminó el formato `.conf`**, por eso todo está en Lua. Mitigación:
   la familia hypr está en `IgnorePkg`, se actualiza a propósito con `ryce-update` y la
   configuración se valida antes contra la versión nueva.
2. **AUR**: en junio de 2026 hubo un secuestro masivo de paquetes huérfanos (campaña
   «Atomic Arch», ~1.579 paquetes con un ladrón de credenciales). Mitigación: este montaje
   no usa AUR.
3. **Playwright** solo da soporte oficial a Debian y Ubuntu. Mitigación: Chromium del sistema
   o un contenedor de Ubuntu para los navegadores de pruebas.

## Hardware: lo que conviene saber
- Todo funciona con el núcleo de serie **menos la Wi‑Fi**: TP‑Link TL‑WN881ND, solo 2,4 GHz y
  **sin Bluetooth**. Usa cable; si algún día quieres Wi‑Fi rápida o Bluetooth, una tarjeta con
  chip **Intel AX210**.
- Gráfica integrada (2 núcleos Xe) con el driver `i915`, decodificación de vídeo por VA‑API
  (`iHD`) y NPU de 13 TOPS (`intel_vpu`). Una IA local no compensa en este equipo: Claude ya
  usa Haiku para títulos y resúmenes.
- **No se instala `thermald`**: hay un informe de que en Arrow Lake de sobremesa limita el
  ancho de banda de memoria.
