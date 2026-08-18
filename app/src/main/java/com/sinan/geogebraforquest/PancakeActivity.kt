package com.sinan.geogebraforquest

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent

/**
 * Normal Horizon OS panel mode: this should feel like ordinary GeoGebra.
 * The headset button in the web shell saves the current .ggb and switches
 * to SpatialGeoGebraActivity.
 */
class PancakeActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setTheme(R.style.PanelAppThemeTransparent)
        setContent {
            GeoGebraWebPanel(spatialMode = false)
        }
    }
}
