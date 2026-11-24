#version 330 core
out vec4 fragColor;

uniform sampler2D u_tex;
uniform vec2 u_resolution;

void main() {
    fragColor = texture(u_tex, gl_FragCoord.xy / u_resolution);
}
