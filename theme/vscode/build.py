#!/usr/bin/env python3
"""Build themes/ryce-vscode.vsix: one VS Code extension, three colour themes.

The themes come straight from contracts/themes/*.json, labelled "Ryce <name>"
("Ryce Origen", "Ryce Grafito", "Ryce Ola", "Ryce Tinta"). A theme switch never rebuilds or
reinstalls anything: the extension carries all three and bin/ryce-theme only
rewrites "workbench.colorTheme" (theme/vscode/settings_edit.py), which VS Code
applies live. Install once, and again after a rebuild:

    code --install-extension themes/ryce-vscode.vsix --force

The editor follows the GTK stance: chrome in bg1, the editor and terminal are the
gate in bg0, hairlines in `line`, selection in a fg0 veil, the pill for the one
primary button. Syntax is near-monochrome: plain text in fg0, structure in fg1,
and colour only where it carries meaning (strings, constants, declarations).

    python3 theme/vscode/build.py           write the VSIX
    python3 theme/vscode/build.py --check   exit 1 if it is missing or stale

No npm, no vsce: a VSIX is a zip with a package.json under extension/. Entries
are written sorted with a fixed timestamp, so the same contracts give the same
bytes.
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from tokens import ThemeError, load_all, scheme  # noqa: E402

OUT = ROOT / "themes" / "ryce-vscode.vsix"
VERSION = "1.0.0"
ENGINE = "^1.80.0"
EPOCH = (1980, 1, 1, 0, 0, 0)


def label(t: dict) -> str:
    """The name VS Code shows and settings.json stores for theme `t`."""
    return f"Ryce {t['name']}"


def _a(hex_: str, alpha: float) -> str:
    return f"{hex_}{round(alpha * 255):02x}"


def colors(t: dict) -> dict[str, str]:
    c, ansi = t["colors"], t["ansi"]
    bg0, bg1, bg2, bg3, line = c["bg0"], c["bg1"], c["bg2"], c["bg3"], c["line"]
    fg0, fg1, fg2, pill, ink = c["fg0"], c["fg1"], c["fg2"], c["pill"], c["ink_on_pill"]
    ok, warn, err, tint = c["ok"], c["warn"], c["err"], c["tint"]
    names = ("Black", "Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White")
    term = {f"terminal.ansi{n}": ansi[i] for i, n in enumerate(names)}
    term |= {f"terminal.ansiBright{n}": ansi[i + 8] for i, n in enumerate(names)}
    return {
        # base
        "foreground": fg1, "descriptionForeground": fg1, "errorForeground": err,
        "icon.foreground": fg1, "focusBorder": fg2, "contrastBorder": "#00000000",
        "selection.background": _a(fg0, 0.2), "widget.shadow": "#00000066" if scheme(t) == "dark" else _a(fg0, 0.16),
        "textLink.foreground": tint, "textLink.activeForeground": fg0,
        "textPreformat.foreground": fg0, "textBlockQuote.background": bg2,
        "textBlockQuote.border": line, "textCodeBlock.background": bg2,
        "progressBar.background": pill, "sash.hoverBorder": fg2,
        # chrome
        "titleBar.activeBackground": bg1, "titleBar.activeForeground": fg1,
        "titleBar.inactiveBackground": bg1, "titleBar.inactiveForeground": fg1,
        "titleBar.border": line,
        "activityBar.background": bg1, "activityBar.foreground": fg0,
        "activityBar.inactiveForeground": fg2, "activityBar.activeBorder": fg0,
        "activityBar.border": line,
        "activityBarBadge.background": pill, "activityBarBadge.foreground": ink,
        "sideBar.background": bg1, "sideBar.foreground": fg1, "sideBar.border": line,
        "sideBarTitle.foreground": fg1,
        "sideBarSectionHeader.background": bg1, "sideBarSectionHeader.foreground": fg1,
        "sideBarSectionHeader.border": line,
        "statusBar.background": bg1, "statusBar.foreground": fg1, "statusBar.border": line,
        "statusBar.noFolderBackground": bg1, "statusBar.debuggingBackground": bg3,
        "statusBar.debuggingForeground": fg0, "statusBarItem.hoverBackground": bg2,
        "statusBarItem.remoteBackground": bg2, "statusBarItem.remoteForeground": fg0,
        "statusBarItem.prominentBackground": bg3,
        "panel.background": bg1, "panel.border": line,
        "panelTitle.activeForeground": fg0, "panelTitle.activeBorder": fg0,
        "panelTitle.inactiveForeground": fg1,
        "editorGroup.border": line, "editorGroupHeader.tabsBackground": bg1,
        "editorGroupHeader.tabsBorder": line, "editorGroupHeader.noTabsBackground": bg1,
        "tab.activeBackground": bg0, "tab.activeForeground": fg0, "tab.activeBorderTop": fg2,
        "tab.activeBorder": bg0, "tab.inactiveBackground": bg1, "tab.inactiveForeground": fg1,
        "tab.unfocusedActiveForeground": fg1, "tab.unfocusedInactiveForeground": fg1,
        "tab.border": line, "tab.hoverBackground": bg2,
        "breadcrumb.background": bg0, "breadcrumb.foreground": fg1,
        "breadcrumb.focusForeground": fg0, "breadcrumb.activeSelectionForeground": fg0,
        # lists, inputs, menus, widgets
        "list.activeSelectionBackground": bg3, "list.activeSelectionForeground": fg0,
        "list.inactiveSelectionBackground": bg2, "list.inactiveSelectionForeground": fg0,
        "list.hoverBackground": bg2, "list.hoverForeground": fg0,
        "list.focusOutline": fg2, "list.focusBackground": bg3,
        "list.highlightForeground": fg0, "list.errorForeground": err,
        "list.warningForeground": warn, "tree.indentGuidesStroke": line,
        "input.background": bg0, "input.foreground": fg0, "input.border": line,
        "input.placeholderForeground": fg1, "inputOption.activeBorder": fg2,
        "inputOption.activeBackground": bg3,
        "inputValidation.errorBorder": err, "inputValidation.errorBackground": bg2,
        "inputValidation.warningBorder": warn, "inputValidation.warningBackground": bg2,
        "inputValidation.infoBorder": fg2, "inputValidation.infoBackground": bg2,
        "dropdown.background": bg2, "dropdown.foreground": fg0, "dropdown.border": line,
        "checkbox.background": bg0, "checkbox.border": line, "checkbox.foreground": fg0,
        "button.background": pill, "button.foreground": ink, "button.hoverBackground": fg1,
        "button.secondaryBackground": bg3, "button.secondaryForeground": fg0,
        "button.secondaryHoverBackground": line,
        "badge.background": bg3, "badge.foreground": fg0,
        "scrollbar.shadow": "#00000000", "scrollbarSlider.background": _a(fg2, 0.25),
        "scrollbarSlider.hoverBackground": _a(fg2, 0.4),
        "scrollbarSlider.activeBackground": _a(fg1, 0.4),
        "menu.background": bg2, "menu.foreground": fg0, "menu.border": line,
        "menu.selectionBackground": bg3, "menu.selectionForeground": fg0,
        "menu.separatorBackground": line,
        "quickInput.background": bg2, "quickInput.foreground": fg0,
        "quickInputList.focusBackground": bg3, "quickInputList.focusForeground": fg0,
        "pickerGroup.border": line, "pickerGroup.foreground": fg1,
        "keybindingLabel.background": bg3, "keybindingLabel.foreground": fg0,
        "keybindingLabel.border": line, "keybindingLabel.bottomBorder": line,
        "notifications.background": bg2, "notifications.foreground": fg0,
        "notifications.border": line, "notificationCenterHeader.background": bg2,
        "notificationsErrorIcon.foreground": err, "notificationsWarningIcon.foreground": warn,
        "notificationsInfoIcon.foreground": fg1,
        "editorWidget.background": bg2, "editorWidget.border": line,
        "editorWidget.foreground": fg0, "editorHoverWidget.background": bg2,
        "editorHoverWidget.border": line, "editorSuggestWidget.background": bg2,
        "editorSuggestWidget.border": line, "editorSuggestWidget.foreground": fg1,
        "editorSuggestWidget.selectedBackground": bg3,
        "editorSuggestWidget.selectedForeground": fg0,
        "editorSuggestWidget.highlightForeground": fg0,
        "peekView.border": line, "peekViewEditor.background": bg1,
        "peekViewResult.background": bg1, "peekViewTitle.background": bg2,
        "peekViewResult.selectionBackground": bg3,
        "peekViewEditor.matchHighlightBackground": _a(fg0, 0.15),
        "peekViewResult.matchHighlightBackground": _a(fg0, 0.15),
        # the editor: the gate
        "editor.background": bg0, "editor.foreground": fg0,
        "editorCursor.foreground": fg0, "editor.lineHighlightBackground": bg1,
        "editor.lineHighlightBorder": "#00000000",
        "editor.selectionBackground": _a(fg0, 0.14),
        "editor.inactiveSelectionBackground": _a(fg0, 0.08),
        "editor.selectionHighlightBackground": _a(fg0, 0.07),
        "editor.wordHighlightBackground": _a(fg0, 0.07),
        "editor.wordHighlightStrongBackground": _a(fg0, 0.11),
        "editor.findMatchBackground": _a(pill, 0.3), "editor.findMatchBorder": fg1,
        "editor.findMatchHighlightBackground": _a(fg1, 0.16),
        "editor.findRangeHighlightBackground": _a(fg0, 0.05),
        "editor.rangeHighlightBackground": _a(fg0, 0.05),
        "editorLineNumber.foreground": fg2, "editorLineNumber.activeForeground": fg0,
        "editorGutter.background": bg0, "editorWhitespace.foreground": line,
        "editorIndentGuide.background1": line, "editorIndentGuide.activeBackground1": fg2,
        "editorRuler.foreground": line, "editorBracketMatch.background": "#00000000",
        "editorBracketMatch.border": fg2, "editorLink.activeForeground": fg0,
        # bracket-pair colouring defaults to gold/orchid/blue: keep pairs in the greys
        **{f"editorBracketHighlight.foreground{i}": fg1 for i in range(1, 7)},
        "editorBracketHighlight.unexpectedBracket.foreground": err,
        "editorCodeLens.foreground": fg1, "editorInlayHint.foreground": fg1,
        "editorInlayHint.background": bg2, "editorGhostText.foreground": _a(fg1, 0.6),
        "editorStickyScroll.background": bg0, "editorStickyScrollHover.background": bg1,
        "editorOverviewRuler.border": line, "minimap.background": bg0,
        "minimapSlider.background": _a(fg2, 0.12),
        "minimapSlider.hoverBackground": _a(fg2, 0.2),
        "editorError.foreground": err, "editorWarning.foreground": warn,
        "editorInfo.foreground": fg1, "editorHint.foreground": fg1,
        "editorOverviewRuler.errorForeground": err, "editorOverviewRuler.warningForeground": warn,
        "editorGutter.addedBackground": ok, "editorGutter.modifiedBackground": fg2,
        "editorGutter.deletedBackground": err,
        "diffEditor.insertedTextBackground": _a(ok, 0.14),
        "diffEditor.removedTextBackground": _a(err, 0.14),
        "diffEditor.insertedLineBackground": _a(ok, 0.06),
        "diffEditor.removedLineBackground": _a(err, 0.06),
        "diffEditor.border": line,
        "gitDecoration.modifiedResourceForeground": warn,
        "gitDecoration.untrackedResourceForeground": ok,
        "gitDecoration.addedResourceForeground": ok,
        "gitDecoration.deletedResourceForeground": err,
        "gitDecoration.conflictingResourceForeground": err,
        "gitDecoration.ignoredResourceForeground": _a(fg1, 0.55),
        # terminal: the same gate, the contract's own ANSI
        "terminal.background": bg0, "terminal.foreground": fg0,
        "terminalCursor.foreground": fg0, "terminal.selectionBackground": _a(fg0, 0.18),
        "terminal.border": line, **term,
    }


def token_colors(t: dict) -> list[dict]:
    c, a = t["colors"], t["ansi"]
    fg0, fg1 = c["fg0"], c["fg1"]
    string, constant, decl = a[2], a[5], a[4]

    def rule(scope: list[str], fg: str | None = None, style: str | None = None) -> dict:
        s = {k: v for k, v in (("foreground", fg), ("fontStyle", style)) if v is not None}
        return {"scope": scope, "settings": s}

    return [
        {"settings": {"foreground": fg0}},
        rule(["comment", "punctuation.definition.comment", "string.comment"], fg1, "italic"),
        rule(["keyword", "storage", "storage.type", "storage.modifier", "variable",
              "entity.name.function", "support.function", "meta.function-call"], fg0),
        rule(["punctuation", "keyword.operator", "meta.brace", "meta.delimiter",
              "keyword.operator.assignment", "punctuation.separator"], fg1),
        rule(["string", "string.quoted", "string.template", "markup.inline.raw",
              "markup.fenced_code", "string.regexp"], string),
        rule(["constant", "constant.numeric", "constant.language", "constant.character",
              "constant.other", "support.constant", "variable.other.enummember",
              "constant.character.escape"], constant),
        rule(["entity.name.function.definition", "meta.definition.function entity.name.function",
              "entity.name.type", "entity.name.class", "entity.name.namespace",
              "entity.name.type.class", "entity.name.section", "entity.name.tag.yaml",
              "support.type.property-name.json", "support.type.property-name.toml"], decl),
        rule(["entity.name.tag", "support.class.component"], fg1),
        rule(["entity.other.attribute-name"], fg1, "italic"),
        rule(["markup.heading", "markup.heading entity.name"], fg0, "bold"),
        rule(["markup.bold"], None, "bold"),
        rule(["markup.italic"], None, "italic"),
        rule(["markup.quote"], fg1, "italic"),
        rule(["markup.underline.link", "string.other.link"], decl, "underline"),
        rule(["markup.inserted"], c["ok"]),
        rule(["markup.deleted"], c["err"]),
        rule(["markup.changed"], c["warn"]),
        rule(["invalid", "invalid.illegal"], c["err"]),
    ]


def semantic(t: dict) -> dict:
    c, a = t["colors"], t["ansi"]
    fg0, decl = c["fg0"], a[4]
    plain = ["function", "method", "class", "type", "interface", "struct", "enum",
             "namespace", "variable", "parameter", "property", "macro"]
    out: dict = {k: fg0 for k in plain}
    out |= {f"{k}.declaration": decl for k in ("function", "method", "class", "type",
                                                "interface", "struct", "enum")}
    out |= {"enumMember": a[5], "variable.readonly": fg0, "number": a[5], "string": a[2],
            "comment": {"foreground": c["fg1"], "italic": True}, "operator": c["fg1"]}
    return out


def theme(t: dict) -> dict:
    return {
        "$schema": "vscode://schemas/color-theme",
        "name": label(t),
        "type": scheme(t),
        "semanticHighlighting": True,
        "colors": colors(t),
        "tokenColors": token_colors(t),
        "semanticTokenColors": semantic(t),
    }


def package(themes: dict[str, dict]) -> dict:
    return {
        "name": "ryce-themes",
        "displayName": "Ryce",
        "description": "Origen, Grafito, Ola, Tinta and Papel: the ryce-pc desktop themes.",
        "version": VERSION,
        "publisher": "ryce",
        "license": "UNLICENSED",
        "engines": {"vscode": ENGINE},
        "categories": ["Themes"],
        "contributes": {"themes": [
            {"label": label(t), "uiTheme": "vs-dark" if scheme(t) == "dark" else "vs",
             "path": f"./themes/ryce-{tid}-color-theme.json"}
            for tid, t in themes.items()
        ]},
    }


def manifest() -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="ryce-themes" Version="{VERSION}" Publisher="ryce" />
    <DisplayName>Ryce</DisplayName>
    <Description xml:space="preserve">Origen, Grafito, Ola and Tinta: the ryce-pc desktop themes.</Description>
    <Categories>Themes</Categories>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{ENGINE}" />
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code" />
  </Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
  </Assets>
</PackageManifest>
"""


CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension=".json" ContentType="application/json" /><Default Extension=".vsixmanifest" ContentType="text/xml" /></Types>
"""


def entries(themes: dict[str, dict]) -> dict[str, str]:
    dump = lambda d: json.dumps(d, indent=2, ensure_ascii=False) + "\n"  # noqa: E731
    out = {"[Content_Types].xml": CONTENT_TYPES, "extension.vsixmanifest": manifest(),
           "extension/package.json": dump(package(themes))}
    for tid, t in themes.items():
        out[f"extension/themes/ryce-{tid}-color-theme.json"] = dump(theme(t))
    return out


def vsix(themes: dict[str, dict]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in sorted(entries(themes).items()):
            info = zipfile.ZipInfo(name, date_time=EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            z.writestr(info, text.encode("utf-8"), compresslevel=9)
    return buf.getvalue()


def main(argv: list[str]) -> int:
    try:
        data = vsix(load_all())
    except ThemeError as e:
        print(f"vscode: {e}", file=sys.stderr)
        return 2
    rel = OUT.relative_to(ROOT)
    if "--check" in argv:
        try:
            cur = OUT.read_bytes()
        except OSError:
            cur = None
        if cur != data:
            print(f"stale: {rel} (run python3 theme/vscode/build.py)")
            return 1
        print(f"vscode: ok ({rel}, {len(data)} bytes)")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_name(OUT.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(OUT)
    print(f"vscode: wrote {rel} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
