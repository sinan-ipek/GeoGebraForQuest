#version 430
#extension GL_ARB_separate_shader_objects: enable
#extension GL_ARB_shading_language_420pack: enable

#include <common.glsl>
#include <app2vertex.glsl>

layout (location = 0) out struct {
    vec2 uv;
    float eyePass;
} vertexOut;

layout (std140, set = 3, binding = 0) uniform MaterialUniform {
    vec4 stereoRect;
} g_MaterialUniform;

void main() {
    App2VertexUnpacked app = getApp2VertexUnpacked();
    vec4 worldPosition = g_PrimitiveUniform.worldFromObject * vec4(app.position, 1.0f);

    vertexOut.uv = app.uv;

    // Meta's own Spatial stereo shaders query the active eye in the vertex
    // stage. Left pass is 0, right pass is 1. All four vertices in a draw pass
    // therefore carry the same eye value into the fragment shader.
    vertexOut.eyePass = float(getStereoPassId());

    gl_Position = getClipFromWorld() * worldPosition;
    postprocessPosition(gl_Position);
}
