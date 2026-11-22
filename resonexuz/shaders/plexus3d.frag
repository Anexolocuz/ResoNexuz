#version 330 core
in float v_depth;
in float v_spec;
in float v_kind;

out vec4 fragColor;

uniform vec3  u_color;
uniform vec3  u_accent;
uniform float u_alpha;

void main() {
    if (v_kind < 0.5) {
        // Faceta triangular translúcida
        vec3 c = mix(u_color, u_accent, clamp(v_spec * 0.65, 0.0, 1.0));
        float a = u_alpha * (0.035 + 0.085 * v_depth + 0.075 * v_spec);
        fragColor = vec4(c, a);
    } else if (v_kind < 1.5) {
        // Arista luminosa
        vec3 c = mix(u_color, vec3(1.0), 0.22 + 0.35 * v_depth + 0.20 * v_spec);
        float a = u_alpha * (0.26 + 0.55 * v_depth + 0.25 * v_spec);
        fragColor = vec4(c, a);
    } else {
        // Nodo estrella / partícula aura con núcleo blanco y halo radial
        vec2 d = gl_PointCoord - vec2(0.5);
        float r = length(d) * 2.0;
        if (r > 1.0) discard;
        float halo = exp(-r * r * 4.8);
        float core = smoothstep(0.36, 0.05, r);
        vec3 c = mix(u_color, vec3(1.0), core * 0.92);
        float a = u_alpha * (halo * (0.50 + 0.45 * v_depth + 0.25 * v_spec) + core * 0.95);
        fragColor = vec4(c, clamp(a, 0.0, 1.0));
    }
}
