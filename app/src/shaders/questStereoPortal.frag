#version 400
#extension GL_ARB_separate_shader_objects: enable
#extension GL_ARB_shading_language_420pack: enable

#include <common.glsl>

layout (std140, set = 3, binding = 0) uniform MaterialUniform {
    vec4 sourceRect;
    vec4 occlusion0;
    vec4 occlusion1;
    vec4 occlusion2;
    vec4 occlusion3;
} g_MaterialUniform;

layout (set = 3, binding = 1) uniform sampler2D albedoSampler;

layout (location = 0) in struct {
    vec2 localUv;
    vec2 sourceUv;
} vertexOut;

layout (location = 0) out vec4 outColor;

bool insideRect(vec2 uv, vec4 rect) {
    return rect.z > 0.0 && rect.w > 0.0 &&
        uv.x >= rect.x && uv.x <= rect.x + rect.z &&
        uv.y >= rect.y && uv.y <= rect.y + rect.w;
}

void main() {
    // Do not hide the complete stereo portal when GeoGebra opens a popup or
    // settings sheet. Punch a hole only where the interactive UI overlaps the
    // 3D canvas so the ordinary WebView can show through underneath.
    if (insideRect(vertexOut.localUv, g_MaterialUniform.occlusion0) ||
        insideRect(vertexOut.localUv, g_MaterialUniform.occlusion1) ||
        insideRect(vertexOut.localUv, g_MaterialUniform.occlusion2) ||
        insideRect(vertexOut.localUv, g_MaterialUniform.occlusion3)) {
        discard;
    }

    outColor = texture(albedoSampler, vertexOut.sourceUv);
}
