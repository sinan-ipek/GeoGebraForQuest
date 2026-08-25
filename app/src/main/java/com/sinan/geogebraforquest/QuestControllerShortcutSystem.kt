package com.sinan.geogebraforquest

import com.meta.spatial.core.Entity
import com.meta.spatial.core.Query
import com.meta.spatial.core.SystemBase
import com.meta.spatial.runtime.ButtonBits
import com.meta.spatial.toolkit.Controller

/**
 * Reads Quest controller button state from the Spatial SDK controller components.
 *
 * A is reserved for the GeoGebra right-click context-menu toggle.
 * B is reserved for the stereo-panel palette toggle.
 *
 * Exp11 also hides Meta's flat panel laser while the pointer is inside the live 3D hole. The
 * controller still targets the transparent A panel, so GeoGebra input/picking is unchanged; the
 * visible depth cue comes from GeoGebra's own stereo 3D cursor/highlight instead.
 */
class QuestControllerShortcutSystem(
    private val activity: SpatialGeoGebraActivity,
) : SystemBase() {

    override fun execute() {
        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }
        val laserEnabled = !DepthPointerState.active

        for (entity in controllers) {
            val controller = entity.getComponent<Controller>()

            if (controller.laserEnabled != laserEnabled) {
                controller.laserEnabled = laserEnabled
                entity.setComponent(controller)
            }

            if (!controller.isActive) continue

            if (isButtonDown(controller, ButtonBits.ButtonA)) {
                activity.onQuestAButtonPressed()
            }

            if (isButtonDown(controller, ButtonBits.ButtonB)) {
                activity.onQuestBButtonPressed(entity)
            }
        }
    }

    private fun isButtonDown(controller: Controller, buttonMask: Int): Boolean {
        return controller.changedButtons.and(buttonMask) == buttonMask &&
            controller.buttonState.and(buttonMask) == buttonMask
    }
}
