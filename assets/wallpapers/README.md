# Wallpaper masters

The user asked for real pictures from the internet, not generated ones (2026-11-09), except
Grafito's dot plates, which stay generated (`theme/wallpaper/scenes.py` for the main one,
`theme/wallpaper/dots.py` for the other two), Tinta's drawing sheets and lock picture, which
the user asked for (2026-11-12, 2026-11-14) and `theme/wallpaper/ink.py` draws, and Papel's two
Tractatus covers, which `theme/wallpaper/paper.py` draws (2026-11-14). Each master here is
already cropped to 16:9 at 2560x1440 (lock pictures at 1920x1080); `scenes.py` derives every
size, the selector and picker thumbs, the launcher panel and the lock picture from it.

Every picture taken from elsewhere is a public-domain work; the drawn ones are the user's
peonza mark, all rights reserved (NOTICE). Which master is a theme's main picture, its lock
and its alternates is the `wallpaper` block of its contract (`contracts/themes/<id>.json`).

| File | Theme | What | Source | Licence |
|---|---|---|---|---|
| `origen-ocaso.jpg` | Origen | Frederic Edwin Church, *Twilight in the Wilderness* (1860) | Wikimedia Commons, `Frederic_Edwin_Church_-_Twilight_in_the_Wilderness.jpg` (Cleveland Museum of Art) | public domain |
| `origen-hudson.jpg` | Origen | Jasper Francis Cropsey, *Autumn – On the Hudson River* (1860) | Wikimedia Commons, `Autumn--On_the_Hudson_River-1860-Jasper_Francis_Cropsey.jpg` (National Gallery of Art) | public domain |
| `ola.jpg` | Ola | Katsushika Hokusai, *The Great Wave off Kanagawa* (c. 1831), aged-paper scan | Wikimedia Commons, `Great_Wave_off_Kanagawa2.jpg` | public domain |
| `ola-lock.jpg` | Ola (lock) | Katsushika Hokusai, *Fine Wind, Clear Morning* (Red Fuji) | Wikimedia Commons, `Red_Fuji_southern_wind_clear_morning.jpg` | public domain |
| `ola-kajikazawa.jpg` | Ola | Katsushika Hokusai, *Kajikazawa in Kai Province* (c. 1830–32), the fisherman on the rock, cropped to 16:9 (the cartouche's top cut) | Wikimedia Commons, `冨嶽三十六景 甲州石班沢 … MET DP141013.jpg` (The Met, Open Access) | public domain (CC0 scan) |
| `ola-naruto.jpg` | Ola | Utagawa Hiroshige, *The Whirlpools of Awa* (1857 triptych), centre crop | Wikimedia Commons, `Awa no Naruto … The Whirlpools of Awa MET DP146864.jpg` (The Met, Open Access) | public domain (CC0 scan) |
| `grafito-ondas.jpg` | Grafito | Two ripple sources interfering, in the main plate's dot matrix | made here: `python3 theme/wallpaper/dots.py` | the user's own |
| `grafito-relieve.jpg` | Grafito | A contour map of a seeded relief in dots, every fifth contour lighter | made here: `python3 theme/wallpaper/dots.py` | the user's own |
| `tinta-plano.jpg` | Tinta | Sheet RY-PZ-001: the user's peonza as a graphite engineering drawing: half-section elevation, plan in a degree ring, a stroboscope of the spinning top, title block. Its frame is a tiled window's edge on the 1920x1080 screen | made here: `python3 theme/wallpaper/ink.py` from the profile in `~/Repos/logo-peonza/src/geometry.mjs` | the user's own mark, all rights reserved |
| `tinta-despiece.jpg` | Tinta | Sheet RY-PZ-002: the peonza exploded into grip, body and steel tip, balloons, parts list, the tip in half-section at 4:1 | made here: `python3 theme/wallpaper/ink.py` | the user's own mark, all rights reserved |
| `tinta-estela.jpg` | Tinta | Sheet RY-PZ-003: the axis's trace from above as the spin decays (precession and nutation), spin and lean against time | made here: `python3 theme/wallpaper/ink.py` | the user's own mark, all rights reserved |
| `tinta-lock.jpg` | Tinta (lock) | The peonza's half-section so close its rim runs off the screen: black body, hatched cut, pale gridded paper and the degree ring (replaces the anime eye, 2026-11-14) | made here: `python3 theme/wallpaper/ink.py` | the user's own mark, all rights reserved |
| `papel.jpg` | Papel | The Tractatus as dots on cream paper (one per proposition, radius from its length, filled to three decimals, a pale halo behind the questions) filling the peonza's silhouette, after the Ludwig Wittgenstein Project's book covers | made here: `python3 theme/wallpaper/paper.py` from `theme/wallpaper/tractatus.json` and `~/Repos/logo-peonza/brand/mark/peonza-silhouette.svg` | the user's own mark, all rights reserved; the text is public domain |
| `papel-lock.jpg` | Papel (lock) | The same book as a cover block with the window hyprlock writes the time in | made here: `python3 theme/wallpaper/paper.py` | public domain text, drawn here |

To replace one: crop the new picture to 16:9, save it here at 2560x1440 (JPEG q≈93,
4:4:4), point `wallpaper.source` (or `lock_source`) of the theme at it and run
`python3 theme/wallpaper/scenes.py`. More pictures for one theme go in its
`wallpaper.alternates` (a list of masters); the wallpaper picker (SUPER+SHIFT+W) or
`ryce-theme wall next|prev|reset|<n>` chooses among them. They never change on their own.
