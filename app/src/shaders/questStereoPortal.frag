#version 400
#extension GL_ARB_separate_shader_objects : enable
#extension GL_ARB_shading_language_420pack : enable

#include <data/shaders/common.glsl>

// sourceRect is normalized in the complete GeoGebra panel texture:
// x = left, y = top, z = width, w = height.
layout (std140, set = 3, binding = 0) uniform MaterialUniform {
  vec4 sourceRect;
} g_MaterialUniform;

layout (set = 3, binding = 1) uniform sampler2D albedoSampler;

layout(location = 0) in struct {
  vec2 uv;
} vertexOut;

layout (location = 0) out vec4 outColor;

void main() {
  float eye = float(getStereoPassId());

  // GeoGebra's Quest renderer writes L and R side-by-side *inside the 3D
  // canvas rectangle*.  Select that rectangle and then the correct half for
  // this Quest eye.  The source texture is the WebView panel's own GPU texture,
  // so this is a direct texture sample: no readback, JPEG, Base64 or Bitmap.
  vec2 sourceUv;
  sourceUv.x = g_MaterialUniform.sourceRect.x
      + g_MaterialUniform.sourceRect.z * (0.5 * vertexOut.uv.x + 0.5 * eye);
  sourceUv.y = g_MaterialUniform.sourceRect.y
      + g_MaterialUniform.sourceRect.w * vertexOut.uv.y;

  outColor = texture(albedoSampler, sourceUv);
}
