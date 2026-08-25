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
 * Exp12 keeps Meta's controller laser visible everywhere, including over the live 3D hole.
 * GeoGebra's own stereo 3D cursor/highlight remains the depth cue, while the visible Meta beam
 * preserves the basic pointing affordance needed to use the panel reliably.
 */
class QuestControllerShortcutSystem(
    private val activity: SpatialGeoGebraActivity,
) : SystemBase() {

    override fun execute() {
        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }

        for (entity in controllers) {
            val controller = entity.getComponent<Controller>()

            // EXP12_VISIBLE_RAY: never hide the system beam over the stereo hole.
            if (!controller.laserEnabled) {
                controller.laserEnabled = true
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
