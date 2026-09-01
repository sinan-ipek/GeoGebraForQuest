#!/usr/bin/env python3
"""Exp16: make Quest stereo eye DOM sources survive renderer/view recreation.

GeoGebra material loading may recreate the 3D WebGL renderer. The historical
Quest patches created a new hidden LEFT eye canvas with the same fixed DOM id
for every renderer instance and kept RIGHT aliased to whichever WebGL canvas
was current when that instance first initialized. Old hidden canvases were not
removed on dispose, so document.getElementById() could return stale sources.

Use one shared global LEFT eye canvas and explicitly rebind the fixed RIGHT id
to the current renderer's WebGL canvas whenever a renderer initializes or a
stereo pair is captured. This makes Browse/Login/material transitions ownership
safe without changing the renderer math or capture quality.
"""

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch-geogebra-quest-v0932.py <geogebra-source-root>")

root = Path(sys.argv[1]).resolve()
path = root / (
    "source/web/web/src/main/java/org/geogebra/web/geogebra3D/web/"
    "euclidian3D/openGL/RendererWithImplW.java"
)
text = path.read_text(encoding="utf-8")

if "EXP16_STEREO_SOURCE_REBIND" in text:
    print("[GGQ] exp16 renderer source rebind already present")
    raise SystemExit(0)

old_block = '''\tprivate HTMLCanvasElement createQuestEyeCanvas(String id) {
\t\tHTMLCanvasElement canvas = (HTMLCanvasElement) DomGlobal.document.createElement("canvas");
\t\tcanvas.id = id;
\t\tcanvas.style.display = "none";
\t\tDomGlobal.document.body.appendChild(canvas);
\t\treturn canvas;
\t}

\tprivate void ensureQuestEyeCanvases() {
\t\tif (questLeftEyeCanvas == null) {
\t\t\tquestLeftEyeCanvas = createQuestEyeCanvas("ggq-renderer-left-eye");
\t\t\tquestLeftEyeContext = Js.uncheckedCast(questLeftEyeCanvas.getContext("2d"));
\t\t}
\t\tif (questRightEyeCanvas == null && webGLCanvas != null) {
\t\t\t// v0.9.20: the final RIGHT_EYE pass already lives in the main WebGL canvas.
\t\t\tquestRightEyeCanvas = Js.uncheckedCast(webGLCanvas.getElement());
\t\t\tquestRightEyeCanvas.id = "ggq-renderer-right-eye";
\t\t}
\t}
'''

new_block = '''\tprivate HTMLCanvasElement createQuestEyeCanvas(String id) {
\t\tHTMLCanvasElement canvas = (HTMLCanvasElement) DomGlobal.document.createElement("canvas");
\t\tcanvas.id = id;
\t\tcanvas.style.display = "none";
\t\tDomGlobal.document.body.appendChild(canvas);
\t\treturn canvas;
\t}

\t// EXP16_STEREO_SOURCE_REBIND: LEFT is one shared DOM source across every
\t// renderer lifecycle; RIGHT is always rebound to the current WebGL canvas.
\tprivate HTMLCanvasElement findQuestEyeCanvas(String id) {
\t\treturn Js.uncheckedCast(DomGlobal.document.getElementById(id));
\t}

\tprivate void bindQuestRightEyeCanvas() {
\t\tif (webGLCanvas == null) {
\t\t\treturn;
\t\t}
\t\tHTMLCanvasElement currentRight = Js.uncheckedCast(webGLCanvas.getElement());
\t\tHTMLCanvasElement existingRight = findQuestEyeCanvas("ggq-renderer-right-eye");
\t\tif (existingRight != null && existingRight != currentRight) {
\t\t\texistingRight.id = "";
\t\t}
\t\tquestRightEyeCanvas = currentRight;
\t\tquestRightEyeCanvas.id = "ggq-renderer-right-eye";
\t}

\tprivate void ensureQuestEyeCanvases() {
\t\tif (questLeftEyeCanvas == null) {
\t\t\tHTMLCanvasElement sharedLeft = findQuestEyeCanvas("ggq-renderer-left-eye");
\t\t\tif (sharedLeft == null) {
\t\t\t\tsharedLeft = createQuestEyeCanvas("ggq-renderer-left-eye");
\t\t\t}
\t\t\tquestLeftEyeCanvas = sharedLeft;
\t\t\tquestLeftEyeContext = Js.uncheckedCast(questLeftEyeCanvas.getContext("2d"));
\t\t}
\t\tbindQuestRightEyeCanvas();
\t}
'''

if old_block not in text:
    raise RuntimeError("exp16 Quest eye-canvas lifecycle anchor not found")
text = text.replace(old_block, new_block, 1)

init_old = '''\t\twebGLCanvas = c;
\t\tggqLastQuestRenderer = this;

\t\tsetRendererImpl'''
init_new = '''\t\twebGLCanvas = c;
\t\tggqLastQuestRenderer = this;
\t\tbindQuestRightEyeCanvas();

\t\tsetRendererImpl'''
if init_old not in text:
    raise RuntimeError("exp16 active-renderer init anchor not found")
text = text.replace(init_old, init_new, 1)

for required in (
    "EXP16_STEREO_SOURCE_REBIND",
    'findQuestEyeCanvas("ggq-renderer-left-eye")',
    'existingRight.id = "";',
    'questRightEyeCanvas.id = "ggq-renderer-right-eye";',
    "bindQuestRightEyeCanvas();",
):
    if required not in text:
        raise RuntimeError(f"exp16 renderer source requirement missing: {required}")

path.write_text(text, encoding="utf-8")
print("[GGQ] exp16 stereo eye sources rebound across renderer/material recreation")
