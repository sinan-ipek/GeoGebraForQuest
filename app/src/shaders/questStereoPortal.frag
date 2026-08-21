#version 400
#extension GL_ARB_separate_shader_objects: enable
#extension GL_ARB_shading_language_420pack: enable

#include <common.glsl>

layout (std140, set = 3, binding = 0) uniform MaterialUniform {
    vec4 sourceRect;
} g_MaterialUniform;

layout (set = 3, binding = 1) uniform sampler2D albedoSampler;

layout (location = 0) in struct {
    vec2 uv;
} vertexOut;

layout (location = 0) out vec4 outColor;

void main() {
    float eye = float(getStereoPassId());

    vec2 sourceUv;
    sourceUv.x = g_MaterialUniform.sourceRect.x +
        g_MaterialUniform.sourceRect.z * (0.5 * vertexOut.uv.x + 0.5 * eye);
    sourceUv.y = g_MaterialUniform.sourceRect.y +
        g_MaterialUniform.sourceRect.w * vertexOut.uv.y;

    outColor = texture(albedoSampler, sourceUv);
}
