package com.sinan.geogebraforquest

import android.content.Context

/**
 * Stores the current .ggb state while switching between Horizon 2D-panel mode
 * and the Spatial SDK activity. It is intentionally local to the device.
 */
object GeoGebraSession {
    private const val PREFS = "geogebra_for_quest"
    private const val KEY_BASE64 = "construction_base64"

    fun save(context: Context, base64: String) {
        if (base64.isBlank()) return
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_BASE64, base64)
            .apply()
    }

    fun load(context: Context): String? =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_BASE64, null)

    fun clear(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_BASE64)
            .apply()
    }
}
