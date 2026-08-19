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
 * v0.2.2 intentionally restores the proven v0.1.2 launcher path exactly:
 * opaque white panel + ordinary embedded GeoGebra WebView.
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
                GeoGebraWebPanel(spatialMode = false)
            }
        }
    }
}
