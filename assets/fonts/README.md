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
| Papel | ui + Obsidian's page | **Literata** 3.103 (TypeTogether, for Google Play Books): a book face drawn for screens, the largest x-height of the serifs measured (0.507), real italic, old-style figures, small caps (`smcp`, `c2sc`), ⁂; variable `opsz` 7–72 and `wght` 200–900 | SIL OFL 1.1 | `github.com/google/fonts` `ofl/literata/Literata[opsz,wght].ttf` and `Literata-Italic[opsz,wght].ttf` (main, 2026-11-19) |
| Papel | display (the hour in words, chapter titles) | **EB Garamond** Italic (Georg Duffner, Octavio Pardo), only the italic: 26 swash capitals (`swsh`, one glyph at a time) and the fleurons ❦ ❧ ☙ | SIL OFL 1.1 | `github.com/google/fonts` `ofl/ebgaramond/EBGaramond-Italic[wght].ttf` (main, 2026-11-19) |
| all | the peonza mark: U+100000–U+100002 (bar), U+100003 (prompt, three cells wide; its state is its colour) | **Ryce Peonza** | the lameiro0x mark, this desktop only | built by `theme/peonza/glyph.py` from `~/Repos/logo-peonza/brand/mark/` |

Ola's interface uses **Inter**, Tinta's **JetBrains Mono**, and every theme's terminals
use **JetBrainsMono Nerd Font**; all come from the Arch repositories (`inter-font`,
`ttf-jetbrains-mono`, `ttf-jetbrains-mono-nerd`). The login page runs as the `greeter`
user, so these files are also copied system-wide (install/system-setup.sh).

| File | sha256 |
|---|---|
| `Doto-Variable.ttf` | `6f4fe7d37853b91df3698daa84cde2dbe1c9695d88c986e6510134910337d426` |
| `EBGaramond-Italic-Variable.ttf` | `bba2c4499c93c9612b90b9825d32b07da52fce2fe57562a1eb6b833553f93c4e` |
| `InstrumentSerif-Italic.ttf` | `08939b8bdf534afec24ae0ef5e03f948940cd9a8fe08e7fecbad040e62327385` |
| `InstrumentSerif-Regular.ttf` | `498efd461f6ddfcb7a111bf9a565709d2085d48201d501ead960d93e84ffbb88` |
| `Literata-Italic-Variable.ttf` | `d483dfaeba9cbf4ce71d32a52ee65df82f7e35b15fff8d1011cdb242d1fcd465` |
| `Literata-Variable.ttf` | `b41138c9373112f32abb589cc22e8674b06ed4048b0c513be922bdd26f274440` |
| `MartianMono-Medium.ttf` | `c4efbbc60eaa94caf3c8a7afb5051e290a42c01e075f97f7e1ee380c70487b96` |
| `MartianMono-Regular.ttf` | `fe1c75feb647d9825c2bee00dc7dedb1ee9f08a0bc3478821f40edd8cb2f1bbd` |
| `RycePeonza.otf` | `0db990d7cefaa5207844c48ade65f495b8c5c26389517943f42bded1e5b58a7c` |
| `SpaceGrotesk-Variable.ttf` | `acad6de1fc93436f5c0f1f4137751ef04f1aea3063e7036535970ffcfbd79f72` |

Update: replace the file, then regenerate this table (`sha256sum assets/fonts/*.{ttf,otf}`).
