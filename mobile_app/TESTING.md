# Verification on this Mac

Verified 2026-09-08:

- Python unit/API suite: **9 passed**, run from repository root with Conda Python 3.12.
- Playwright + installed Chrome: **3 passed** — desktop 1440×1000, phone-width 390×844, and actual MP3/cover uploads to a temporary dry-run server. Transport interactions, settings, search, no horizontal overflow and absence of page JavaScript errors checked in the responsive tests.
- Desktop and phone screenshots visually inspected; generated screenshots are in `test-results/` after the browser run.
- JavaScript syntax, deployment shell syntax and iOS Info.plist validation passed.
- Android Gradle `assembleDebug`: **BUILD SUCCESSFUL**, using Java 21 and SDK 35. APK signature verification passed. Package `com.gibson.g1dancer`, version 2.0 / code 2, minimum API 23.
- Capacitor Android and iOS asset sync passed.

Not verified: physical Android/iPhone installation, iOS compilation/signing or simulator (full Xcode is absent), offline hotspot networking on native devices, Bluetooth audio output and actual robot motion. Browser phone-width tests are not native-device tests. Dry-run audio completes immediately; simulated UI playback tests cover transport state transitions without sound or movement.
