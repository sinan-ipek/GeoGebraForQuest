package com.sinan.geogebraforquest

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color

/** Normal Horizon OS panel entry point. */
class PancakeActivity : ComponentActivity() {
    private var hasPaused = false

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

    override fun onPause() {
        hasPaused = true
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        // Returning from the spatial host must restore an ordinary, non-transparent
        // GeoGebra 3D canvas. Recreate from the latest autosaved .ggb snapshot.
        if (hasPaused) {
            hasPaused = false
            recreate()
        }
    }
}
