package com.sinan.geogebraforquest

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent

/**
 * Non-launcher fallback panel kept during v0.2 development.
 * The real application entry point is SpatialGeoGebraActivity.
 */
class PancakeActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setTheme(R.style.PanelAppThemeTransparent)
        setContent {
            GeoGebraWebPanel()
        }
    }
}
