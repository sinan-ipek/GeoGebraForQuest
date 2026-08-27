package com.sinan.geogebraforquest

import android.util.Log
import com.meta.spatial.core.Query
import com.meta.spatial.core.SystemBase
import com.meta.spatial.toolkit.AvatarSystem
import com.meta.spatial.toolkit.Controller

/**
 * Exp22 recovery for the system Android document picker boundary.
 *
 * ACTION_OPEN_DOCUMENT temporarily leaves immersive Spatial mode. Exp21 proved that
 * rewriting Controller components is not the right repair. Meta Spatial SDK 0.13.2
 * assigns controller/hand representation visibility to AvatarSystem, so this system
 * repairs only that owning layer after returning from DocumentsUI.
 *
 * Controller components are strictly read-only here. Their presence, active state and
 * laserEnabled state are logged so a failed Quest test distinguishes an AvatarSystem
 * visibility failure from a lower VRFeature/device-session failure.
 */
class QuestControllerPresentationRecoverySystem : SystemBase() {

    companion object {
        private const val TAG = "GGQ-ControllerReturn"
        private const val DEFAULT_RECOVERY_FRAMES = 240
    }

    @Volatile
    private var recoveryFrames = 0

    @Volatile
    private var recoveryReason = ""

    // A true cached AvatarSystem flag does not prove that its controller scene
    // representation survived the immersive -> DocumentsUI -> immersive boundary.
    // Force a real false -> true edge across two Spatial frames after each request.
    @Volatile
    private var forceVisibilityResetPhase = 0

    fun requestRecovery(
        reason: String,
        frames: Int = DEFAULT_RECOVERY_FRAMES,
    ) {
        recoveryReason = reason
        forceVisibilityResetPhase = 1
        if (frames > recoveryFrames) {
            recoveryFrames = frames
        }
    }

    override fun execute() {
        val remaining = recoveryFrames
        if (remaining <= 0) return

        val avatarSystem = try {
            systemManager.findSystem<AvatarSystem>()
        } catch (t: Throwable) {
            if (remaining == DEFAULT_RECOVERY_FRAMES || remaining % 60 == 0) {
                Log.w(TAG, "AvatarSystem not available yet; reason=$recoveryReason", t)
            }
            return
        }

        val controllersWereVisible = avatarSystem.getShowControllers()
        when (forceVisibilityResetPhase) {
            1 -> {
                // First Spatial frame: explicitly drop the controller representation.
                avatarSystem.setShowControllers(false)
                forceVisibilityResetPhase = 2
                Log.i(
                    TAG,
                    "forced AvatarSystem controller visibility FALSE; reason=$recoveryReason",
                )
            }
            2 -> {
                // Next Spatial frame: rebuild/re-show it through the owning system.
                avatarSystem.setShowControllers(true)
                forceVisibilityResetPhase = 0
                Log.i(
                    TAG,
                    "forced AvatarSystem controller visibility TRUE; reason=$recoveryReason",
                )
            }
            else -> {
                if (!controllersWereVisible) {
                    avatarSystem.setShowControllers(true)
                }
            }
        }

        var localControllers = 0
        var activeControllers = 0
        var laserEnabledControllers = 0

        val controllers = Query.where { has(Controller.id) }.eval().filter { it.isLocal() }
        for (entity in controllers) {
            localControllers++
            val controller = entity.getComponent<Controller>()
            if (controller.isActive) activeControllers++
            if (controller.laserEnabled) laserEnabledControllers++
        }

        if (
            remaining == DEFAULT_RECOVERY_FRAMES ||
            remaining % 30 == 0 ||
            !controllersWereVisible ||
            localControllers == 0 ||
            forceVisibilityResetPhase != 0
        ) {
            Log.i(
                TAG,
                "reason=$recoveryReason remaining=$remaining " +
                    "avatarShowControllersBefore=$controllersWereVisible " +
                    "avatarShowControllersNow=${avatarSystem.getShowControllers()} " +
                    "resetPhase=$forceVisibilityResetPhase " +
                    "localControllers=$localControllers active=$activeControllers " +
                    "laserEnabled=$laserEnabledControllers",
            )
        }

        recoveryFrames = remaining - 1
    }
}
