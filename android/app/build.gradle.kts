plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

// Bundle the shared gateway sources from the repository root into the app's Python
// directory, so the APK always runs the same gateway.py / models.json / dashboard.
val repoRoot = rootDir.parentFile
val pyDir = file("src/main/python")
copy {
    from(repoRoot) { include("gateway.py", "models.json", "dashboard.html", "game.html", "solitaire.html") }
    into(pyDir)
}

android {
    namespace = "com.mcubed.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.mcubed.app"
        minSdk = 26
        targetSdk = 35
        versionCode = (System.getenv("MCUBED_VERSION_CODE") ?: "1").toInt()
        versionName = System.getenv("MCUBED_VERSION_NAME") ?: "0.1.0"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Signed with the debug key unless you configure your own keystore.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

chaquopy {
    defaultConfig {
        version = "3.13"
    }
}
