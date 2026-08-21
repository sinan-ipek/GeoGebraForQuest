#version 430
#extension GL_ARB_separate_shader_objects: enable
#extension GL_ARB_shading_language_420pack: enable

#include <common.glsl>
#include <app2vertex.glsl>

layout (location = 0) out struct {
    vec2 localUv;
    vec2 sourceUv;
} vertexOut;

layout (std140, set = 3, binding = 0) uniform MaterialUniform {
    vec4 sourceRect;
    vec4 occlusion0;
    vec4 occlusion1;
    vec4 occlusion2;
    vec4 occlusion3;
} g_MaterialUniform;

void main() {
    App2VertexUnpacked app = getApp2VertexUnpacked();
    vec4 worldPosition = g_PrimitiveUniform.worldFromObject * vec4(app.position, 1.0f);

    // Meta's own stereo shaders query getStereoPassId() in the vertex stage.
    // Left pass is 0 and right pass is 1. Split only the measured GeoGebra 3D
    // source rectangle, not the complete WebView texture.
    float eye = float(getStereoPassId());

    vertexOut.localUv = app.uv;
    vertexOut.sourceUv.x = g_MaterialUniform.sourceRect.x +
        g_MaterialUniform.sourceRect.z * (0.5 * app.uv.x + 0.5 * eye);
    vertexOut.sourceUv.y = g_MaterialUniform.sourceRect.y +
        g_MaterialUniform.sourceRect.w * app.uv.y;

    gl_Position = getClipFromWorld() * worldPosition;
    postprocessPosition(gl_Position);
}
