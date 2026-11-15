#version 440
// Origen: the film still keeps running. Fine luminance grain, renewed 24 times a second
// like a projected print, and the key light from the upper left breathing over 20 s.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float time;
    vec2 resolution;
};
layout(binding = 1) uniform sampler2D source;

// PCG-style integer hash: stable on every GPU, unlike fract(sin(x)).
float hash(uvec3 v) {
    v = v * 1664525u + 1013904223u;
    v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y;
    v ^= v >> 16u;
    v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y;
    return float(v.x & 0xffffu) / 65535.0;
}

void main() {
    vec2 uv = qt_TexCoord0;
    vec3 c = texture(source, uv).rgb;
    float lum = dot(c, vec3(0.2126, 0.7152, 0.0722));

    // Breathing: the light the scene is lit by swells and ebbs by a few levels over 20 s,
    // nothing in the far corners.
    vec2 d = (uv - vec2(0.30, 0.22)) * vec2(1.0, 1.7);
    float key = exp(-dot(d, d) * 2.2);
    float breath = sin(6.2831853 * time / 20.0);
    c = c * (1.0 + 0.06 * breath * key) + 0.005 * breath * key;

    // Grain: two pixels per grain, strongest in the mid-tones, a whisper in the blacks.
    float frame = floor(time * 24.0);
    uvec2 cell = uvec2(uv * resolution / 2.0);
    float n = hash(uvec3(cell, uint(frame))) + hash(uvec3(cell + 7u, uint(frame) + 3u)) - 1.0;
    c += n * (0.009 + 0.040 * sqrt(lum) * (1.0 - lum));

    fragColor = vec4(c, 1.0) * qt_Opacity;
}
