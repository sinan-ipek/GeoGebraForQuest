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
 * Right Grip is an exp13 momentary 3D-view rotate modifier while the pointer is over the live 3D
 * hole. Releasing Grip restores the exact GeoGebra tool that was active before the press.
 */
class QuestControllerShortcutSystem(
    private val activity: SpatialGeoGebraActivity,
) : SystemBase() {

    private var rightGripRotateActive = false

    override fun execute() {
        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }

        for (entity in controllers) {
            val controller = entity.getComponent<Controller>()

            // EXP12_VISIBLE_RAY remains frozen: the native beam always reaches A.
            if (!controller.laserEnabled) {
                controller.laserEnabled = true
                entity.setComponent(controller)
            }

            if (!controller.isActive) continue

            if (controller.isPressed(ButtonBits.ButtonSqueezeR)) {
                if (DepthPointerState.active && !rightGripRotateActive) {
                    rightGripRotateActive = activity.onQuestGripRotatePressed()
                }
            }

            if (
                rightGripRotateActive &&
                controller.isReleased(ButtonBits.ButtonSqueezeR)
            ) {
                activity.onQuestGripRotateReleased()
                rightGripRotateActive = false
            }

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
