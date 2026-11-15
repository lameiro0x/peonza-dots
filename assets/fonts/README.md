# Vendored fonts

None of these is in the Arch repositories (and the AUR is off limits), so they ship
here. `install/links.tsv` deploys this folder to `~/.local/share/fonts/ryce/`;
fontconfig picks them up on the next `fc-cache`. Licences in `licenses/`.

| Theme | Role | Family | Licence | Source |
|---|---|---|---|---|
| Origen | ui + display | **Martian Mono** (Evil Martians) | SIL OFL 1.1 | copied from `~/Repos/logo-peonza/assets/fonts/` (the brand's typeface) |
| Grafito | ui | **Space Grotesk** (Florian Karsten) | SIL OFL 1.1 | `github.com/google/fonts` `ofl/spacegrotesk/SpaceGrotesk[wght].ttf` (main, 2026-11-09) |
| Grafito | display (≥ 26 px only) | **Doto** (Óliver Lalan) | SIL OFL 1.1 | `github.com/google/fonts` `ofl/doto/Doto[ROND,wght].ttf` (main, 2026-11-09) |
| Ola | display (clocks) | **Instrument Serif** (Rodrigo Fuenzalida, Jordan Egstad) | SIL OFL 1.1 | `github.com/google/fonts` `ofl/instrumentserif/InstrumentSerif-{Regular,Italic}.ttf` (main, 2026-11-09) |
| Papel | ui + display | **Space Mono** (Colophon Foundry), Regular and Bold: the face of the Ludwig Wittgenstein Project's covers | SIL OFL 1.1 | `github.com/google/fonts` `ofl/spacemono/SpaceMono-{Regular,Bold}.ttf` (main, 2026-11-14) |
| all | the peonza mark: U+100000–U+100002 (bar), U+100003 (prompt, three cells wide; its state is its colour) | **Ryce Peonza** | the lameiro0x mark, this desktop only | built by `theme/peonza/glyph.py` from `~/Repos/logo-peonza/brand/mark/` |

Ola's interface uses **Inter**, Tinta's **JetBrains Mono**, and every theme's terminals
use **JetBrainsMono Nerd Font**; all come from the Arch repositories (`inter-font`,
`ttf-jetbrains-mono`, `ttf-jetbrains-mono-nerd`). The login page runs as the `greeter`
user, so these files are also copied system-wide (install/system-setup.sh).

| File | sha256 |
|---|---|
| `Doto-Variable.ttf` | `6f4fe7d37853b91df3698daa84cde2dbe1c9695d88c986e6510134910337d426` |
| `InstrumentSerif-Italic.ttf` | `08939b8bdf534afec24ae0ef5e03f948940cd9a8fe08e7fecbad040e62327385` |
| `InstrumentSerif-Regular.ttf` | `498efd461f6ddfcb7a111bf9a565709d2085d48201d501ead960d93e84ffbb88` |
| `MartianMono-Medium.ttf` | `c4efbbc60eaa94caf3c8a7afb5051e290a42c01e075f97f7e1ee380c70487b96` |
| `MartianMono-Regular.ttf` | `fe1c75feb647d9825c2bee00dc7dedb1ee9f08a0bc3478821f40edd8cb2f1bbd` |
| `RycePeonza.otf` | `0db990d7cefaa5207844c48ade65f495b8c5c26389517943f42bded1e5b58a7c` |
| `SpaceGrotesk-Variable.ttf` | `acad6de1fc93436f5c0f1f4137751ef04f1aea3063e7036535970ffcfbd79f72` |
| `SpaceMono-Bold.ttf` | `405e73d41afb7e5906efce206a326af5c956f38e255f35421c260e861e599c59` |
| `SpaceMono-Regular.ttf` | `95837e182baeeada83368f7748db28357f0a1b75c6b84ff7065b5edf933c8e18` |

Update: replace the file, then regenerate this table (`sha256sum assets/fonts/*.{ttf,otf}`).
