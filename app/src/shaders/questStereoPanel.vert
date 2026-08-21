#version 430
#extension GL_ARB_separate_shader_objects: enable
#extension GL_ARB_shading_language_420pack: enable

#include <common.glsl>
#include <app2vertex.glsl>

layout (location = 0) out struct {
    vec2 uv;
} vertexOut;

layout (std140, set = 3, binding = 0) uniform MaterialUniform {
    vec4 stereoRect;
    vec4 occlusion0;
    vec4 occlusion1;
    vec4 occlusion2;
    vec4 occlusion3;
    vec4 layoutInfo;
} g_MaterialUniform;

void main() {
    App2VertexUnpacked app = getApp2VertexUnpacked();
    vec4 worldPosition = g_PrimitiveUniform.worldFromObject * vec4(app.position, 1.0f);
    vertexOut.uv = app.uv;
    gl_Position = getClipFromWorld() * worldPosition;
    postprocessPosition(gl_Position);
}
