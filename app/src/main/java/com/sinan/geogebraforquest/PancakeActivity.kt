package com.sinan.geogebraforquest

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color

/**
 * Normal Horizon OS panel mode.
 *
 * The app always starts here because this exact 2D WebView path has already been
 * proven on Quest. Selecting GeoGebra's replacement Anaglyph/Stereo control then
 * asks Android to enter the Spatial host while preserving the construction.
 */
class PancakeActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setTheme(R.style.PanelAppTheme)
        setContent {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.White),
            ) {
                GeoGebraWebPanel(spatialMode = false, startStereo = false)
            }
        }
    }
}
