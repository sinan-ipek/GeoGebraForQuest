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
 */
class QuestControllerShortcutSystem(
    private val activity: SpatialGeoGebraActivity,
) : SystemBase() {

    override fun execute() {
        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }
        for (entity in controllers) {
            val controller = entity.getComponent<Controller>()
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
