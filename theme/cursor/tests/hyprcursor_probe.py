"""Load the ryce-peonza hyprcursor theme through libhyprcursor's C API and print, per shape,
"<shape> <frames> <hotspot x> <hotspot y>" at the size given. Run in its own process (by
test_build.py) so XDG_DATA_DIRS points it at a throwaway icons folder.

    python3 hyprcursor_probe.py SIZE SHAPE...
"""
import ctypes
import ctypes.util
import sys


class Style(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint)]


class Image(ctypes.Structure):
    _fields_ = [("surface", ctypes.c_void_p), ("size", ctypes.c_int), ("delay", ctypes.c_int),
                ("hotspot_x", ctypes.c_int), ("hotspot_y", ctypes.c_int)]


LOG = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p)


def main(argv: list[str]) -> int:
    lib = ctypes.CDLL(ctypes.util.find_library("hyprcursor"))
    lib.hyprcursor_manager_create_with_logger.restype = ctypes.c_void_p
    lib.hyprcursor_manager_create_with_logger.argtypes = [ctypes.c_char_p, LOG]
    lib.hyprcursor_manager_valid.argtypes = [ctypes.c_void_p]
    lib.hyprcursor_load_theme_style.argtypes = [ctypes.c_void_p, Style]
    lib.hyprcursor_get_cursor_image_data.restype = ctypes.POINTER(ctypes.POINTER(Image))
    lib.hyprcursor_get_cursor_image_data.argtypes = [ctypes.c_void_p, ctypes.c_char_p, Style,
                                                     ctypes.POINTER(ctypes.c_int)]
    lib.hyprcursor_cursor_image_data_free.argtypes = [ctypes.POINTER(ctypes.POINTER(Image)), ctypes.c_int]
    lib.hyprcursor_manager_free.argtypes = [ctypes.c_void_p]
    logs: list[str] = []
    keep = LOG(lambda _level, msg: logs.append(msg.decode(errors="replace")))
    manager = lib.hyprcursor_manager_create_with_logger(b"ryce-peonza", keep)
    if not manager or not lib.hyprcursor_manager_valid(manager):
        print("hyprcursor_probe: theme ryce-peonza not found or invalid\n" + "\n".join(logs[-20:]), file=sys.stderr)
        return 1
    style = Style(int(argv[0]))
    if not lib.hyprcursor_load_theme_style(manager, style):
        print("hyprcursor_probe: load_theme_style failed\n" + "\n".join(logs[-20:]), file=sys.stderr)
        return 1
    for shape in argv[1:]:
        n = ctypes.c_int(0)
        data = lib.hyprcursor_get_cursor_image_data(manager, shape.encode(), style, ctypes.byref(n))
        if n.value == 0:
            print(f"hyprcursor_probe: no image for {shape}", file=sys.stderr)
            return 1
        first = data[0].contents
        print(shape, n.value, first.hotspot_x, first.hotspot_y)
        lib.hyprcursor_cursor_image_data_free(data, n)
    lib.hyprcursor_manager_free(manager)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
