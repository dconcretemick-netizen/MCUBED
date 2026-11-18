plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

// Bundle the shared gateway sources from the repository root into the app's Python
// directory, so the APK always runs the same gateway.py / models.json / dashboard.
val repoRoot = rootDir.parentFile
val pyDir = file("src/main/python")
copy {
    from(repoRoot) { include("gateway.py", "models.json", "dashboard.html", "game.html", "solitaire.html", "tetris.html", "platformer.html", "news.json", "build_info.json") }
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

    // One permanent release key (from CI secrets) so each new APK installs as an update over the last one.
    val ks = System.getenv("MCUBED_KEYSTORE_FILE")
    signingConfigs {
        if (ks != null && file(ks).exists()) {
            create("mcubed") {
                storeFile = file(ks)
                storeType = "pkcs12"
                storePassword = System.getenv("MCUBED_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("MCUBED_KEY_ALIAS") ?: "mcubed"
                keyPassword = System.getenv("MCUBED_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Local builds without the key fall back to the debug key.
            signingConfig = signingConfigs.findByName("mcubed") ?: signingConfigs.getByName("debug")
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
