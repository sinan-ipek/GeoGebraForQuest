from pathlib import Path

p = Path('app/src/main/assets/web/quest-stereo-capture.js')
s = p.read_text(encoding='utf-8')

needle = """    const originalColorMask = gl.colorMask.bind(gl);\n    const originalClear = gl.clear.bind(gl);\n    const state = stateOf(gl);\n\n"""
if needle not in s:
    raise SystemExit('eye-id test: hookContext insertion point missing')

insert = """    const originalColorMask = gl.colorMask.bind(gl);\n    const originalClear = gl.clear.bind(gl);\n    const state = stateOf(gl);\n\n    // v0.13.22 A-eye identification diagnostic.\n    //\n    // The stereo pair captured for B is intentionally NOT modified. We stamp the\n    // visible GeoGebra framebuffer only AFTER each eye has already been read with\n    // readPixels(). LEFT gets a red top strip; RIGHT gets a blue top strip. The\n    // right-eye pass clears the left marker before it renders, so whichever strip\n    // survives into A tells us which GeoGebra eye CEF actually presents.\n    function stampVisibleEyeMarker(which) {\n      try {\n        const oldMask = gl.getParameter(gl.COLOR_WRITEMASK);\n        const oldClear = gl.getParameter(gl.COLOR_CLEAR_VALUE);\n        const oldScissorEnabled = gl.isEnabled(gl.SCISSOR_TEST);\n        const oldScissor = gl.getParameter(gl.SCISSOR_BOX);\n\n        const width = Math.max(1, gl.drawingBufferWidth | 0);\n        const height = Math.max(1, gl.drawingBufferHeight | 0);\n        const barHeight = Math.max(36, Math.min(96, Math.round(height * 0.075)));\n\n        originalColorMask(true, true, true, true);\n        gl.enable(gl.SCISSOR_TEST);\n        gl.scissor(0, Math.max(0, height - barHeight), width, barHeight);\n\n        if (which === 'left') {\n          gl.clearColor(1.0, 0.0, 0.0, 1.0);\n        } else {\n          gl.clearColor(0.0, 0.20, 1.0, 1.0);\n        }\n        originalClear(gl.COLOR_BUFFER_BIT);\n\n        if (oldClear && oldClear.length >= 4) {\n          gl.clearColor(oldClear[0], oldClear[1], oldClear[2], oldClear[3]);\n        }\n        if (oldScissor && oldScissor.length >= 4) {\n          gl.scissor(oldScissor[0], oldScissor[1], oldScissor[2], oldScissor[3]);\n        }\n        if (!oldScissorEnabled) gl.disable(gl.SCISSOR_TEST);\n        if (oldMask && oldMask.length >= 4) {\n          originalColorMask(!!oldMask[0], !!oldMask[1], !!oldMask[2], !!oldMask[3]);\n        }\n      } catch (error) {\n        console.warn('[GGQ Eye-ID] marker failed', error);\n      }\n    }\n\n"""
s = s.replace(needle, insert, 1)

left_old = """      if (kind === 'right') {\n        if (state.phase === 'left') {\n          if (state.captureThisFrame && state.leftPixels) {\n            state.leftReady = readInto(gl, state.leftPixels);\n          }\n          state.phase = 'right';\n          state.needsRightColorClear = true;\n        }\n        return originalColorMask(true, true, true, true);\n      }\n"""
left_new = """      if (kind === 'right') {\n        if (state.phase === 'left') {\n          if (state.captureThisFrame && state.leftPixels) {\n            state.leftReady = readInto(gl, state.leftPixels);\n          }\n          // B's LEFT pixels have already been captured above. This red marker is\n          // only for the visible A framebuffer and will be erased by RIGHT's clear.\n          stampVisibleEyeMarker('left');\n          state.phase = 'right';\n          state.needsRightColorClear = true;\n        }\n        return originalColorMask(true, true, true, true);\n      }\n"""
if left_old not in s:
    raise SystemExit('eye-id test: LEFT->RIGHT transition missing')
s = s.replace(left_old, left_new, 1)

right_old = """      if (kind === 'all') {\n        if (state.phase === 'right') {\n          if (state.captureThisFrame && state.leftReady && state.rightPixels) {\n            if (readInto(gl, state.rightPixels)) emitStereoPair(state);\n          }\n          resetPhase(state);\n        }\n        return originalColorMask(true, true, true, true);\n      }\n"""
right_new = """      if (kind === 'all') {\n        if (state.phase === 'right') {\n          if (state.captureThisFrame && state.leftReady && state.rightPixels) {\n            if (readInto(gl, state.rightPixels)) emitStereoPair(state);\n          }\n          // B's RIGHT pixels have already been captured above. If A presents the\n          // final RIGHT framebuffer, this BLUE strip is what the user will see.\n          stampVisibleEyeMarker('right');\n          resetPhase(state);\n        }\n        return originalColorMask(true, true, true, true);\n      }\n"""
if right_old not in s:
    raise SystemExit('eye-id test: RIGHT->ALL transition missing')
s = s.replace(right_old, right_new, 1)

# Durable marker for workflow verification.
s = s.replace("window.__ggqStereoCaptureV071 = true;",
              "window.__ggqStereoCaptureV071 = true;\n  window.__ggqAEyeIdDiagnostic = 'LEFT_RED_RIGHT_BLUE';", 1)

p.write_text(s, encoding='utf-8')
print('v0.13.22 A eye-ID diagnostic applied: LEFT=red, RIGHT=blue')
