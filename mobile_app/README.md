# G1 DANCER — shared desktop, Android and iPhone experience

The responsive HTML/CSS/JavaScript interface in `../g1_dancer/web/` runs in desktop browsers and in native Capacitor 7 Android/iOS shells. No cloud, CDN, Spotify login or subscription is involved. All UI assets are bundled. Songs play on the **development PC's speaker**, not the phone. Files selected from cloud storage must be downloaded onto your phone before joining the offline hotspot.

## Try it on this Mac

From the repository root:

```sh
/Users/110663/miniconda3/bin/python -m g1_dancer.preview
```

This opens `http://127.0.0.1:8788/?demo`: six sample tiles and simulated transport controls, with no robot connection. Remove `?demo` to try actual uploads against a temporary dry-run backend. Audio is simulated in dry-run; preview data disappears when the server exits. Ctrl-C stops the preview. This explicit Python path avoids the broken Homebrew Python launcher on this Mac.

## Use with the G1

1. Copy and reinstall the updated Python package on the development PC using the repository's deployment instructions. Restart `g1-dancer.service` after updating. Existing dance JSON and music files remain in its configured data directory.
2. Join its Wi-Fi hotspot and keep the connection even if the phone reports “no internet.”
3. Desktop: open `http://10.42.0.1:8787`. Mobile: launch the installed app and allow local-network access if prompted. The default connection is the same address.
4. Select a tile, then **Edit track** to upload an MP3 or PNG/JPEG cover. Every dance has generated artwork until you choose a cover. **Refresh** loads newly added dance definitions. Search and filters narrow the collection.
5. The round **Play** button starts the selected dance with its song after a safety confirmation, then changes to Pause/Resume. The preset-motion shelf exposes every named gesture in Unitree's G1 arm-action map; selecting one also requires safety confirmation. The square button stops/resets playback. An existing robot action may finish after pause; these controls are not an emergency stop.
6. **•••** opens connection settings, startup instructions and a collapsible activity log. Closing the app does not stop playback. No seeking/volume slider is shown because the existing playback API does not support these features.

The server must already be running to accept commands. Enable automatic startup once on the development PC:

```sh
systemctl --user enable --now g1-dancer.service
```

For startup before login, an administrator can enable lingering for the service user with `sudo loginctl enable-linger unitree` on the development PC. From your Mac you can start it using:

```sh
ssh unitree@10.42.0.1 systemctl --user start g1-dancer.service
```

The shared app does **not** include SSH or Bluetooth pairing controls. Pair the speaker on the development PC using the existing CLI. The old Tk controller remains available with `python -m g1_dancer.cli gui --classic`. A stopped HTTP server cannot start itself; the native apps cannot start it via HTTP. The no-token API is intended only for a trusted hotspot, never public networks.

## Install on Android

Copy `G1Dancer.apk` from this folder onto your phone, open it in Files, and permit installation from that source. This is a debug-signed sideload build, not a Play Store release. It uses the same app ID as the previous Android controller and a newer version code. If Android reports a signing mismatch, back up settings before uninstalling the old controller (songs are stored on the G1 PC, not in the phone app).

## Install on iPhone

An iPhone cannot directly install an APK. This folder includes a native Xcode project; a signed iOS app must be built for your device.

1. Install full **Xcode 16 or newer** from the Mac App Store, launch it and finish component installation. This Mac currently has only command-line tools; no signed iOS app or simulator build has been produced here.
2. While online, run:

   ```sh
   cd mobile_app
   npm ci
   npm run sync
   npm run ios
   ```

3. In Xcode, add your Apple account under Settings → Accounts. Select the **App** target → **Signing & Capabilities**, enable automatic signing and select your team. If necessary choose a unique bundle identifier. Swift Package Manager resolves Capacitor automatically; CocoaPods is not required.
4. Connect and trust your iPhone by USB, enable **Developer Mode** when requested, choose it as the run destination, then click ▶ Run. Allow **Local Network** access when the app connects. Finish the first build while online, then join the G1 hotspot.
5. For Mac-only iOS testing, select an installed iPhone simulator as the destination and Run. Use your Mac-hosted preview's address in settings for dry-run testing; simulator testing does not prove physical-phone hotspot connectivity.

A free Apple Personal Team can run a development build on your own device but provisioning expires after seven days, requiring a rebuild. TestFlight/distribution requires the appropriate paid developer membership and signing workflow. See [Apple's device run guide](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices), [Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device), and [membership limits](https://developer.apple.com/help/account/basics/about-your-developer-account).

Without installing a native build, Safari on your iPhone can also open `http://10.42.0.1:8787` while joined to the hotspot. It uses the identical interface. The G1 server must be reachable; this is not an offline-cached PWA.

## Rebuild and test

Node 20+, Java 21 and Android SDK 35 are required for Android. Install dependencies while online; normal use needs no internet.

```sh
npm ci
npm run sync
cd android
./gradlew assembleDebug
```

APK output: `android/app/build/outputs/apk/debug/app-debug.apk`. Native assets are generated from the shared source by `npm run sync`; do not edit `www/` or native `public/` copies directly.

Backend tests from repository root: `python -m unittest discover -s tests -v`. With the safe preview running on port 8788, run `npx playwright test` in this folder. The included configuration uses this Mac's installed Chrome; change `executablePath` for another machine. These test desktop/mobile-width layouts, settings, search, simulated transport and real dry-run upload endpoints. Native device, Bluetooth, physical robot and iOS WebView tests still require the corresponding hardware/toolchain.
