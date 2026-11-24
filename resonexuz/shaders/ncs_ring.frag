#version 330 core
out vec4 fragColor;

uniform vec2  u_resolution;
uniform float u_time;
uniform float u_base_hue;       // color base (tono + velocidad del beat)
uniform float u_harmony;        // desplazamiento de matiz del segundo acento: 0.4167 (150°) o 0.3333 (120°)
uniform float u_peak1;          // pico primario: bombo / drop -> color opuesto (180°)
uniform float u_peak2;          // pico secundario: caja / agudos -> color complementario dividido
uniform float u_bass;           // envolvente de graves suavizada
uniform float u_idle;           // 0 = audio activo, 1 = reposo (respiración)
uniform float u_balance;        // balance estéreo [-1 izq .. +1 der]
uniform float u_ring_size;
uniform float u_reactivity;
uniform float u_density;
uniform float u_guide_inner;
uniform float u_guide_outer;
uniform vec2  u_const_rot;      // (cos(rot), sin(rot)) precalculado en CPU
uniform float u_const_scale;    // (14.0 * u_density) * (1.0 - bass * 0.08)

// Controles de calidad en vivo
uniform int   u_q_constellation; // 0 = apagada, 1 = solo puntos, 2 = completa
uniform int   u_q_glow;          // 0 = líneas nítidas sin halos exp(), 1 = halos y resplandor
uniform int   u_q_dither;        // 0 = sin ruido final, 1 = con dithering anti-bandas
uniform int   u_q_echo;          // 0 = omitir ecos en calidad ultra baja, 1 = permitir ecos

uniform float u_spectrum_l[64];
uniform float u_spectrum_r[64];

// Configuración de los 3 niveles (0 = interior/central, 1 = medio, 2 = exterior)
uniform int   u_lvl_enabled[3];
uniform int   u_lvl_mode[3];       // 0 = SDF 2D, 1 = 3D segmentos
uniform float u_lvl_scale[3];
uniform float u_lvl_react[3];
uniform int   u_lvl_echo_on[3];
uniform float u_lvl_echo_amp[3];
uniform float u_lvl_echo_off[3];
uniform int   u_lvl_echo_peak[3];
uniform float u_lvl_echo_thr[3];
uniform int   u_lvl_color[3];      // 0 = base, 1 = opp1 (180°), 2 = opp2 (armonía)

uniform sampler2D u_sdf0;
uniform sampler2D u_sdf1;
uniform sampler2D u_sdf2;

const float SDF_EXTENT = 1.25;

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

float hashf(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

vec2 dotPos(vec2 id) {
    float n = hashf(id);
    vec2 h = vec2(n, hashf(id + n + 17.3));
    return sin(h * 6.2831 + u_time * vec2(0.55, 0.43)) * 0.4;
}

float sampleArr(float arr[64], float t) {
    float idx = clamp(t * 63.0, 0.0, 63.0);
    int i0 = int(floor(idx));
    int i1 = min(i0 + 1, 63);
    return mix(arr[i0], arr[i1], fract(idx));
}

float sampleStereoSpec(float t, float xCoord) {
    float sl = sampleArr(u_spectrum_l, t);
    float sr = sampleArr(u_spectrum_r, t);
    float side = smoothstep(-0.025, 0.025, xCoord);
    return mix(sl, sr, side);
}

float segment(vec2 p, vec2 a, vec2 b) {
    vec2 pa = p - a, ba = b - a;
    float t = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-5), 0.0, 1.0);
    float d = length(pa - ba * t);
    return smoothstep(0.035, 0.006, d) * smoothstep(1.3, 0.5, length(ba));
}

// Constelación interna: mode 1 = solo puntos, mode 2 = puntos + red de segmentos
vec2 constellation(vec2 p, int mode) {
    vec2 gv = fract(p) - 0.5;
    vec2 id = floor(p);
    if (mode == 1) {
        float dots = 0.0;
        for (int y = -1; y <= 1; y++) {
            for (int x = -1; x <= 1; x++) {
                vec2 cell = id + vec2(float(x), float(y));
                vec2 pt = vec2(float(x), float(y)) + dotPos(cell);
                float tw = 0.55 + 0.45 * sin(u_time * 2.0 + hashf(cell + 3.7) * 6.2831);
                dots += smoothstep(0.075, 0.012, length(gv - pt)) * tw;
            }
        }
        return vec2(dots, 0.0);
    }

    vec2 pts[9];
    float tw[9];
    int k = 0;
    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            vec2 cell = id + vec2(float(x), float(y));
            pts[k] = vec2(float(x), float(y)) + dotPos(cell);
            tw[k] = 0.55 + 0.45 * sin(u_time * 2.0 + hashf(cell + 3.7) * 6.2831);
            k++;
        }
    }
    float lines = 0.0, dots = 0.0;
    for (int i = 0; i < 9; i++) {
        lines += segment(gv, pts[4], pts[i]);
        dots += smoothstep(0.075, 0.012, length(gv - pts[i])) * tw[i];
    }
    lines += segment(gv, pts[1], pts[3]) + segment(gv, pts[1], pts[5])
           + segment(gv, pts[7], pts[3]) + segment(gv, pts[7], pts[5]);
    return vec2(dots, lines);
}

vec4 evalSdf(int lvl, vec2 uv, float scale) {
    vec2 p = uv / max(scale, 0.05);
    vec2 clamped = clamp(p, vec2(-SDF_EXTENT), vec2(SDF_EXTENT));
    float extra = length(p - clamped);
    vec2 tc = (clamped / SDF_EXTENT) * 0.5 + 0.5;
    vec4 s = (lvl == 0) ? texture(u_sdf0, tc)
           : (lvl == 1) ? texture(u_sdf1, tc)
                        : texture(u_sdf2, tc);
    // Reescalar distancia a espacio UV real y sumar distancia fuera de la caja
    s.r = (s.r + extra) * scale;
    return s;
}

vec3 pickColor(int role, vec3 col_base, vec3 col_opp1, vec3 col_opp2) {
    if (role == 1) return col_opp1;
    if (role == 2) return col_opp2;
    return col_base;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;
    float r = length(uv);

    float bass = mix(u_bass, 0.30 + 0.25 * sin(u_time * 0.9), u_idle);
    float calm = clamp(u_idle, 0.0, 1.0);

    // Paleta base + acentos
    vec3 col_base = hsv2rgb(vec3(u_base_hue, 0.82, 0.95));
    vec3 col_opp1 = hsv2rgb(vec3(fract(u_base_hue + 0.50), 0.92, 1.00));
    vec3 col_opp2 = hsv2rgb(vec3(fract(u_base_hue + u_harmony), 0.88, 1.00));
    vec3 gray = vec3(0.19, 0.20, 0.235);
    col_base = mix(col_base, gray, calm);
    col_opp1 = mix(col_opp1, gray, calm);
    col_opp2 = mix(col_opp2, gray, calm);

    // Fondo Tokyo Night + resplandor sutil desplazado por el balance estéreo
    vec3 bg = vec3(0.035, 0.04, 0.065);
    if (u_q_glow != 0) {
        vec2 stereo_center = vec2(u_balance * 0.14 * (1.0 - calm), 0.0);
        float r_glow = length(uv - stereo_center);
        bg += col_base * exp(-r_glow * 3.8) * (0.10 + bass * 0.14);
    }

    // Evaluar cada nivel y calcular la máscara interior del dibujo más cercano al centro
    float inner_mask = 0.0;
    float central_sd = 10.0;
    float central_disp = 0.0;
    bool central_found = false;

    vec3 lines_accum = vec3(0.0);
    float core_alpha = 0.0;
    vec3 core_col = vec3(0.0);

    for (int lvl = 0; lvl < 3; lvl++) {
        if (u_lvl_enabled[lvl] == 0) continue;

        float scale = (u_lvl_scale[lvl] + bass * 0.035) * u_ring_size;
        float react = u_lvl_react[lvl] * u_reactivity;
        vec3 base_c = pickColor(u_lvl_color[lvl], col_base, col_opp1, col_opp2);
        vec3 echo_c = (u_lvl_color[lvl] == 1) ? col_opp2 : col_opp1;

        float d_base = 10.0;
        float spec = 0.0;
        float closed_flag = 1.0;
        float disp = 0.0;
        vec4 sdf = vec4(0.0);

        if (u_lvl_mode[lvl] == 0) {
            float max_disp = max(0.04, (u_guide_outer - 0.15) * scale * 0.65);
            bool echo_active = (u_lvl_echo_on[lvl] != 0 && u_q_echo != 0);
            float max_echo = echo_active
                ? (u_lvl_echo_off[lvl] * u_ring_size + max_disp * u_lvl_echo_amp[lvl])
                : max_disp;
            float lvl_reach = scale * u_guide_outer + max(max_disp, max_echo) + (u_q_glow != 0 ? 0.38 : 0.05);
            if (r > lvl_reach) {
                if (!central_found) central_found = true;
                continue;
            }

            sdf = evalSdf(lvl, uv, scale);
            float t_spec = sdf.g;
            closed_flag = sdf.a;
            spec = sampleStereoSpec(t_spec, uv.x);
            spec = mix(spec, 0.10 + 0.06 * sin(u_time * 1.3 + t_spec * 3.0), u_idle);
            // Desplazamiento paralelo acotado por la circunferencia exterior para evitar pellizcos
            disp = min(spec * 0.14 * u_ring_size * react, max_disp);
            d_base = (closed_flag > 0.5) ? abs(sdf.r - disp) : abs(sdf.r - disp * 0.6);

            if (!central_found) {
                central_found = true;
                central_sd = sdf.r;
                central_disp = disp;
                if (closed_flag > 0.5) {
                    inner_mask = smoothstep(disp - 0.004, disp - 0.04, sdf.r);
                } else {
                    float safe_r = u_guide_inner * scale * 1.3;
                    inner_mask = smoothstep(safe_r, safe_r - 0.04, r);
                }
            }
        } else {
            // Nivel en modo 3D plexus (se dibuja en la segunda pasada hardware)
            if (!central_found) {
                central_found = true;
                float safe_r = max(0.10, u_guide_inner * scale * 1.45);
                inner_mask = smoothstep(safe_r, safe_r - 0.04, r);
                central_sd = r - safe_r;
                central_disp = 0.0;
            }
            continue;
        }

        // Eco propio de este nivel (reutiliza sdf.r ya muestreado)
        if (u_lvl_echo_on[lvl] != 0 && u_q_echo != 0) {
            float echo_disp = u_lvl_echo_off[lvl] * u_ring_size + disp * u_lvl_echo_amp[lvl];
            float echo_d = abs(sdf.r - echo_disp);
            float echo_k;
            if (u_lvl_echo_peak[lvl] != 0) {
                // Eco invisible en reposo/valles: solo aparece suavemente cerca del máximo de la onda
                float thr = u_lvl_echo_thr[lvl];
                float crest_e = clamp(spec + max(u_peak1, u_peak2) * 0.20, 0.0, 1.0);
                float vis = smoothstep(max(0.05, thr - 0.15), min(1.0, thr + 0.05), crest_e) * (1.0 - calm);
                echo_k = vis * (0.85 + 0.35 * u_peak1);
            } else {
                echo_k = (0.58 + 0.30 * spec + 0.35 * u_peak1) * (1.0 - 0.45 * calm);
            }
            float echo_line = smoothstep(0.0032, 0.0005, echo_d);
            if (u_q_glow != 0) {
                echo_line += exp(-echo_d * 42.0) * 0.26;
            }
            lines_accum += echo_c * echo_line * echo_k;
        }

        // Halo y núcleo de la línea del nivel
        float thick = (lvl == 0 ? 0.011 : 0.0055) + spec * 0.005 + u_peak1 * 0.003;
        float core = smoothstep(thick, 0.0012, d_base);
        if (u_q_glow != 0) {
            float halo_k = (lvl == 0) ? (0.55 + u_peak1 * 0.75) : (0.32 + u_peak2 * 0.45);
            float halo = exp(-d_base * (22.0 - u_peak1 * 6.0)) * halo_k * (1.0 - 0.5 * calm);
            vec3 halo_col = mix(base_c, col_opp2, u_peak2);
            lines_accum += halo_col * halo;
        }

        float crest = clamp(u_peak1 * (0.35 + 0.9 * spec), 0.0, 1.0);
        vec3 line_col = (lvl == 0) ? mix(base_c, col_opp1, crest) : base_c;

        float w_core = core * (lvl == 0 ? 1.0 : 0.78);
        core_col = mix(core_col, mix(line_col, vec3(1.0), (0.45 + 0.25 * u_peak1) * (1.0 - 0.8 * calm)), w_core);
        core_alpha = max(core_alpha, w_core);
    }

    // Constelación interna confinada únicamente al dibujo más cercano al centro
    vec3 inner = vec3(0.0);
    if (u_q_constellation != 0 && inner_mask > 0.001) {
        mat2 m = mat2(u_const_rot.x, -u_const_rot.y, u_const_rot.y, u_const_rot.x);
        vec2 p = (m * uv) * u_const_scale;
        vec2 c = constellation(p, u_q_constellation);
        float edge_fade = smoothstep(0.0, 0.08, inner_mask);
        vec3 dot_col = mix(col_base, col_opp2, clamp(u_peak2 * 1.25, 0.0, 1.0));
        vec3 line_col = mix(col_base, col_opp2, clamp(u_peak2, 0.0, 1.0));
        inner += dot_col * c.x * (0.35 + u_peak2 * 1.1);
        inner += line_col * c.y * (0.10 + u_peak2 * 0.55);
        inner *= edge_fade * inner_mask;
    }

    // Onda de choque desde el nivel central
    float shock = 0.0;
    if (u_q_glow != 0 && u_peak1 > 0.01) {
        float shock_d = abs(central_sd - (central_disp + 0.02 + u_peak1 * 0.07));
        shock = smoothstep(0.008, 0.001, shock_d) * u_peak1 * 0.75;
    }

    vec3 color = bg + inner + lines_accum + col_opp1 * shock;
    color = mix(color, core_col, core_alpha);

    // Viñeta suave y ruido mínimo para evitar bandas
    color *= 1.0 - 0.35 * smoothstep(0.55, 1.1, r);
    if (u_q_dither != 0) {
        color += (hashf(gl_FragCoord.xy + fract(u_time)) - 0.5) / 255.0;
    }
    fragColor = vec4(clamp(color, 0.0, 1.0), 1.0);
}
