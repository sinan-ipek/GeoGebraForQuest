plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.jetbrains.kotlin.android)
    alias(libs.plugins.meta.spatial.plugin)
    alias(libs.plugins.compose.compiler)
}

android {
    namespace = "com.sinan.geogebraforquest"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.sinan.geogebraforquest"
        minSdk = 34
        targetSdk = 34
        versionCode = 130
        versionName = "0.9.30-exp42-smooth-grip-move"

        ndkVersion = "27.0.12077973"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        // SideQuest streams APKs through /data/local/tmp/_stream.apk. Keeping
        // the large Meta native libraries compressed makes that transfer much
        // smaller; Android extracts them while installing.
        jniLibs.useLegacyPackaging = true
        resources.excludes.add("META-INF/LICENSE")
    }

    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    debugImplementation(libs.androidx.ui.tooling)

    implementation("androidx.webkit:webkit:1.12.1")

    implementation(libs.meta.spatial.sdk.base)
    implementation(libs.meta.spatial.sdk.vr)
    implementation(libs.meta.spatial.sdk.compose)
    implementation(libs.meta.spatial.sdk.toolkit)
    implementation(libs.meta.spatial.sdk.isdk)
}

// v0.9.30-exp40-ime-grip-latch lives only on experimental-embedded-stereo.
// Stable v0.9.29 remains frozen on stable-v0.9.29-palette.
// Exp39 calls LoginOperationW directly once per ACK transaction; no repeated
// MessageEvent restart. Grip is temporary Move in 2D/3D and restores prior tool.
// Right-thumb graph-canvas zoom works in both 2D and 3D.
// Exp37 packaging remains: compressed native libraries and aligned resources.
// Exp35 keeps Exp34 token-first OAuth/session ownership and the exact Exp27
// local-file/XR runtime. Login change is limited to IME email->password focus.
// Right thumbstick UP/DOWN is deterministic 3D zoom while the depth pointer is
// inside the live 3D hole; duplicate ISDK panel scroll is suppressed briefly.
spatial {
    allowUsageDataCollection.set(true)
    shaders {
        sources.add(project.layout.projectDirectory.dir("src/shaders"))
    }
}
