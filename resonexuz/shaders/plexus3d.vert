#version 330 core
layout(location = 0) in vec2  in_pos;
layout(location = 1) in float in_depth;
layout(location = 2) in float in_spec;
layout(location = 3) in float in_kind;
layout(location = 4) in float in_size;

uniform float u_aspect;
uniform float u_point_scale;

out float v_depth;
out float v_spec;
out float v_kind;

void main() {
    gl_Position = vec4(in_pos.x * 2.0 / max(u_aspect, 0.1), in_pos.y * 2.0, 0.0, 1.0);
    gl_PointSize = in_size * u_point_scale;
    v_depth = in_depth;
    v_spec = in_spec;
    v_kind = in_kind;
}
