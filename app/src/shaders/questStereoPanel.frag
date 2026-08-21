#version 430
#extension GL_ARB_separate_shader_objects: enable
#extension GL_ARB_shading_language_420pack: enable

#include <common.glsl>

layout (std140, set = 3, binding = 0) uniform MaterialUniform {
    vec4 stereoRect;
} g_MaterialUniform;

layout (set = 3, binding = 1) uniform sampler2D albedoSampler;

layout (location = 0) in struct {
    vec2 uv;
    float eyePass;
} vertexOut;

layout (location = 0) out vec4 outColor;

bool inRect(vec2 p, vec4 r) {
    return r.z > 0.0 && r.w > 0.0 &&
        p.x >= r.x && p.x <= r.x + r.z &&
        p.y >= r.y && p.y <= r.y + r.w;
}

void main() {
    vec2 uv = vertexOut.uv;

    // All normal GeoGebra UI remains mono. Only the measured WebGL 3D canvas
    // rectangle is interpreted as L|R SBS.
    if (!inRect(uv, g_MaterialUniform.stereoRect)) {
        outColor = texture(albedoSampler, uv);
        return;
    }

    vec2 local =
        (uv - g_MaterialUniform.stereoRect.xy) /
        g_MaterialUniform.stereoRect.zw;

    float eye = clamp(vertexOut.eyePass, 0.0, 1.0);

    vec2 sourceUv;
    sourceUv.x = g_MaterialUniform.stereoRect.x +
        g_MaterialUniform.stereoRect.z * (0.5 * local.x + 0.5 * eye);
    sourceUv.y = g_MaterialUniform.stereoRect.y +
        g_MaterialUniform.stereoRect.w * local.y;

    vec4 sampled = texture(albedoSampler, sourceUv);

    // Diagnostic marker: a tiny yellow square at the upper-left corner of the
    // 3D rectangle proves that the *visible real panel* has switched to this
    // v0.9.9 material. Remove it after the eye-routing path is confirmed.
    if (local.x < 0.025 && local.y < 0.035) {
        outColor = mix(sampled, vec4(1.0, 0.92, 0.05, 1.0), 0.85);
        return;
    }

    outColor = sampled;
}
