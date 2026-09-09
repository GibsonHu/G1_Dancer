# G1 Dancer

G1 Dancer plays music and starts saved G1 dance routines from a browser, desktop app, Android app, or iPhone app. Keep the physical E-stop ready and clear the motion area before starting a dance.

## Robot development PC setup

The development PC stays connected to the G1 by Ethernet and runs the controller service. The official Unitree Python SDK is included in this repository, so install this project while the PC has internet access to fetch its CycloneDDS, NumPy, and OpenCV requirements.

```bash
python3 -m pip install --user .
g1-dancer init --interface eth0
g1-dancer serve
```

Replace `eth0` with the Ethernet interface connected to the robot. This creates the config at `~/.config/g1-dancer/config.yaml` and sample dances at `~/.local/share/g1-dancer/routines`.

The default service address is `http://10.42.0.1:8787`. To start it automatically after login:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/g1-dancer.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now g1-dancer.service
```

In the app’s Settings, choose the music output:

- **G1 speaker** needs `ffmpeg` and `unitree_sdk2py`; it streams PCM audio through `AudioClient.PlayStream()`.
- **Bluetooth speaker** and **USB speaker** use the development PC’s currently selected system sound output.

## Local PC setup

Connect the local PC to the development PC’s G1 hotspot, then open:

```text
http://10.42.0.1:8787
```

To use the command line from the local PC, install this project and run:

```bash
g1-dancer remote --url http://10.42.0.1:8787 add-mp3 clap-wave song.mp3
g1-dancer remote --url http://10.42.0.1:8787 play clap-wave --yes
```

For a safe local interface preview with simulated playback:

```bash
PYTHONPATH=src /Users/110663/miniconda3/bin/python -m g1_dancer.preview
```

## App setup

The same interface is used by the desktop browser, Android app, and iPhone app. Open **Settings**, enter the development PC address, choose the music output, and connect to the robot.

- **Desktop:** open `http://10.42.0.1:8787` in a browser.
- **Android:** install `mobile_app/G1Dancer.apk`.
- **iPhone:** open `mobile_app/ios/App/App.xcworkspace` in Xcode, choose a signing team, then run it on the device.

Use the library to select a dance, add an MP3 or cover with the gear button, and press Play. The app asks for a safety confirmation before it starts robot motion.
