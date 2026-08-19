package com.sinan.geogebraforquest

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier

/**
 * The real GeoGebra UI Activity.
 *
 * This is intentionally kept as an ordinary Android Activity because that path
 * has already been proven to render the local GeoGebra bundle correctly on Quest.
 * SpatialGeoGebraActivity embeds this Activity itself as a spatial panel.
 */
class PancakeActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setTheme(R.style.PanelAppThemeTransparent)
        setContent {
            Box(modifier = Modifier.fillMaxSize()) {
                GeoGebraWebPanel()
            }
        }
    }
}
