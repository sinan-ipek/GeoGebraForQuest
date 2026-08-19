package com.sinan.geogebraforquest

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier

/**
 * GeoGebra panel used only inside the Spatial SDK immersive host.
 *
 * This is a dedicated ActivityPanelRegistration target. Meta's official samples
 * use Activity-backed panels for full Android UI, including WebView-based panels.
 * Keeping the WebView inside a normal Android Activity avoids placing AndroidView/
 * WebView directly inside a Spatial Compose panel, which was the unstable path in
 * v0.3.4.
 */
class SpatialPanelActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setTheme(R.style.PanelAppThemeTransparent)
        setContent {
            Box(modifier = Modifier.fillMaxSize()) {
                GeoGebraWebPanel(
                    spatialMode = true,
                    startStereo = true,
                )
            }
        }
    }
}
