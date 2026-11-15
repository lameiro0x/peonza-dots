-- Session environment. Hyprland sets XDG_CURRENT_DESKTOP, XDG_SESSION_TYPE and
-- WAYLAND_DISPLAY itself; autostart.lua hands them to systemd --user.

-- The peonza cursor (theme/cursor/build.py, deployed to ~/.local/share/icons),
-- the same name and size as apps/gtk-*/settings.ini and theme/gsettings.sh. The
-- theme ships both formats: Hyprland draws its hyprcursor build (HYPRCURSOR_*);
-- XWayland, Qt and GTK read the XCursor one (XCURSOR_*). 32 px: on the 24"
-- 1080p screens the old 24 got lost on light and mid-tone grounds.
hl.env("HYPRCURSOR_THEME", "ryce-peonza")
hl.env("HYPRCURSOR_SIZE", "32")
hl.env("XCURSOR_THEME", "ryce-peonza")
hl.env("XCURSOR_SIZE", "32")

-- Wayland first, X11 only for apps built without it.
hl.env("QT_QPA_PLATFORM", "wayland;xcb")
hl.env("QT_QPA_PLATFORMTHEME", "qt6ct")
hl.env("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")
hl.env("GDK_BACKEND", "wayland,x11")
hl.env("SDL_VIDEODRIVER", "wayland")
hl.env("CLUTTER_BACKEND", "wayland")
hl.env("ELECTRON_OZONE_PLATFORM_HINT", "auto")
-- Java/Swing tools (Burp Suite, Ghidra) draw blank grey windows under a
-- non-reparenting window manager without this.
hl.env("_JAVA_AWT_WM_NONREPARENTING", "1")
