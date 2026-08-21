#version 400
#extension GL_ARB_separate_shader_objects : enable
#extension GL_ARB_shading_language_420pack : enable

#include <data/shaders/common.glsl>

layout (std140, set = 3, binding = 0) uniform MaterialUniform {
  vec4 stereoRect;
  vec4 occlusion0;
  vec4 occlusion1;
  vec4 occlusion2;
  vec4 occlusion3;
  vec4 layoutInfo;
} g_MaterialUniform;

layout (set = 3, binding = 1) uniform sampler2D albedoSampler;

layout(location = 0) in struct {
  vec2 uv;
} vertexOut;

layout (location = 0) out vec4 outColor;

bool inRect(vec2 p, vec4 r) {
  return r.z > 0.0 && r.w > 0.0 &&
      p.x >= r.x && p.x <= r.x + r.z &&
      p.y >= r.y && p.y <= r.y + r.w;
}

bool inOcclusion(vec2 p) {
  int count = int(g_MaterialUniform.layoutInfo.x + 0.5);
  if (count > 0 && inRect(p, g_MaterialUniform.occlusion0)) return true;
  if (count > 1 && inRect(p, g_MaterialUniform.occlusion1)) return true;
  if (count > 2 && inRect(p, g_MaterialUniform.occlusion2)) return true;
  if (count > 3 && inRect(p, g_MaterialUniform.occlusion3)) return true;
  return false;
}

void main() {
  vec2 uv = vertexOut.uv;

  // UI pixels remain ordinary mono panel pixels for both eyes. A popup/dialog
  // that overlaps the 3D view also stays mono and therefore remains readable.
  if (g_MaterialUniform.layoutInfo.y < 0.5 ||
      !inRect(uv, g_MaterialUniform.stereoRect) ||
      inOcclusion(uv)) {
    outColor = texture(albedoSampler, uv);
    return;
  }

  // GeoGebra's source renderer writes full-colour L|R directly into the 2x-wide
  // WebGL backing store of the 3D canvas. The panel texture flattens that canvas
  // into stereoRect; sample the appropriate half for this Quest eye.
  vec2 local = (uv - g_MaterialUniform.stereoRect.xy) /
      g_MaterialUniform.stereoRect.zw;
  float eye = float(getStereoPassId());

  vec2 sourceUv;
  sourceUv.x = g_MaterialUniform.stereoRect.x +
      g_MaterialUniform.stereoRect.z * (0.5 * local.x + 0.5 * eye);
  sourceUv.y = g_MaterialUniform.stereoRect.y +
      g_MaterialUniform.stereoRect.w * local.y;

  outColor = texture(albedoSampler, sourceUv);
}
