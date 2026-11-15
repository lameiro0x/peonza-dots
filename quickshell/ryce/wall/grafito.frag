#version 440
// Grafito: a slow wave travels across the dot plate, swelling each dot it crosses.
// The plate is redrawn from the wallpaper itself: every 15 px cell (1080 / 72 rows, as
// theme/wallpaper/scenes.py draws it) samples its own dot scaled about the cell centre,
// so the dots stay round, anti-aliased and aligned to the grid.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float time;
    vec2 resolution;
};
layout(binding = 1) uniform sampler2D source;

const float ROWS = 72.0;
const float PERIOD = 25.0;        // seconds per sweep; divides the 1000 s time cycle

void main() {
    float pitch = resolution.y / ROWS;
    vec2 px = qt_TexCoord0 * resolution;
    vec2 centre = (floor(px / pitch) + 0.5) * pitch;

    // One soft band, diagonal from the upper left, crossing the screen once per period.
    vec2 cu = centre / resolution.y;
    float along = dot(cu, normalize(vec2(1.0, 0.55))) / 2.6;
    float x = fract(along - time / PERIOD) - 0.5;
    float band = exp(-x * x / 0.0035);

    // The plate's small dots (ink `line`) may double; the mark's big ones (up to 0.4
    // pitch) grow 20 %, so every dot still fits its own cell.
    float ink = texture(source, centre / resolution).g;
    float s = 1.0 + band * mix(1.0, 0.2, smoothstep(0.18, 0.35, ink));
    vec3 c = texture(source, (centre + (px - centre) / s) / resolution).rgb;
    c *= 1.0 + 0.25 * band;

    fragColor = vec4(c, 1.0) * qt_Opacity;
}
