# G1 Dancer

G1 Dancer is a small, offline-first controller that runs on the development PC connected to a Unitree G1. All dance definitions live on that development PC. It attaches an MP3 to an existing dance, plays music through the PC's paired Bluetooth speaker, and triggers the G1 timeline at the same monotonic start time. A second computer has only two normal operations over the direct Wi-Fi/hotspot link: add an MP3 to an existing dance, or play that dance. No cloud service is involved.

The new shared desktop, Android and iOS interface is documented in [mobile_app/README.md](mobile_app/README.md). It includes cover-art tiles, MP3/image upload, search, refresh, music transport and a three-dot settings menu. Desktop users open `http://10.42.0.1:8787`; Android users install `mobile_app/G1Dancer.apk`; iPhone users build the included Xcode project or use Safari. The Tk GUI remains available as a legacy controller.

Safe local preview on this Mac: `/Users/110663/miniconda3/bin/python -m g1_dancer.preview`. This uses temporary data and simulated playback, with no robot connection. `gui` now opens the shared web interface; use `gui --classic` for the older desktop window with SSH startup controls.

## Safety first

This software can move a full-size humanoid. Test with the robot suspended or in Unitree's recommended safe test setup, keep people and obstacles out of reach, keep the physical E-stop ready, and start in `--dry-run`. The caller must pass `--yes` before motion. Audio cancellation is immediate; `StopMove` is sent on stop or playback failure, but it is not a replacement for the physical E-stop.

The two bundled examples use Unitree's high-level `LocoClient` and `G1ArmActionClient`. Action availability varies with G1 model and firmware, so confirm each action on your own robot before building a longer routine.

## Development-PC setup

Use Python 3.10 or newer. While the PC still has internet access, install the official Unitree SDK and this project. Unitree currently documents `unitree_sdk2_python` with CycloneDDS 0.10.2; follow its own installation instructions for your robot image.

```bash
python3 -m pip install ./unitree_sdk2_python
python3 -m pip install --user .
g1-dancer init --interface eth0
```

Replace `eth0` with the Ethernet interface connected to the G1 (`ip link` shows names). Initialization creates `~/.config/g1-dancer/config.yaml`, mode 0600, and two sample routines under `~/.local/share/g1-dancer/routines`.

The editable YAML configuration contains the data directory, G1 network interface, API address and port, dry-run setting, upload limit, and preferred audio player. See [config.example.yaml](config.example.yaml) for every available setting. You can maintain alternate configurations and select one with `--config`:

```bash
g1-dancer --config ~/.config/g1-dancer/rehearsal.yaml serve
```

### Copy this project to the development PC

The development PC provides its own Wi-Fi hotspot at `10.42.0.1`. Connect this workstation to that hotspot first, then use the included SSH deployment script. It defaults to `unitree@10.42.0.1`, copies files with `rsync`, excludes caches and local build artifacts, and never deletes files already present on the development PC.

```bash
scripts/copy_to_dev_pc.sh
```

The default destination is `~/g1-dancer`. To select another SSH port or destination:

```bash
scripts/copy_to_dev_pc.sh --port 2222 unitree@g1-dev.local /home/unitree/g1-dancer
```

Then connect to the development PC and install/initialize the app:

```bash
ssh unitree@10.42.0.1
cd ~/g1-dancer
python3 -m pip install --user .
g1-dancer init --interface eth0
```

Test the complete scheduler without importing the robot SDK:

```bash
g1-dancer list
g1-dancer run clap-wave --dry-run --yes
g1-dancer serve --dry-run
```

## Legacy local-computer GUI

Install this project on the local/controller computer as well, connect it to the development PC's hotspot, and launch:

```bash
g1-dancer gui --classic
```

The GUI defaults to API URL `http://10.42.0.1:8787` and SSH target `unitree@10.42.0.1`. It can:

- start the installed `g1-dancer.service` remotely;
- refresh the dropdown of dances already stored on the development PC;
- select and attach or replace an MP3;
- play the selected dance's linked MP3 without moving the robot;
- play a dance, pause/resume its audio and remaining timeline, or reset it;
- show or hide a timestamped activity log for connection, upload, and playback events;
- open a short Info guide explaining the normal workflow and safety behavior.

The UI separates network/service settings into the **Connection** tab and dance, music, and large playback controls into the **Dance** tab. It includes the blurred `dancer_1.png` background asset in the installed application.

The desktop window uses the bundled G1 Dancer app icon, a close-up humanoid face with a cyan dance emblem.

Use **Refresh dances** whenever routines are added directly to the development PC. The list also refreshes automatically after remote startup and after an MP3 upload, and marks dances that currently have an MP3 attached.

Remote startup is deliberately non-interactive and requires SSH key authentication. Configure it once from the local computer while connected to the hotspot:

```bash
ssh-copy-id unitree@10.42.0.1
ssh unitree@10.42.0.1 systemctl --user status g1-dancer.service
```

On Linux, install the `python3-tk` OS package if Tkinter is not included with Python. A pause suspends audio and prevents future timeline steps from starting, then sends `StopMove`; a Unitree canned action that has already started may still finish. Use the physical E-stop for immediate safety intervention.

## Bluetooth speaker

On Linux, install/configure BlueZ and PipeWire or PulseAudio in advance. Put the speaker in pairing mode, then run:

```bash
g1-dancer speaker scan --seconds 10
g1-dancer speaker pair AA:BB:CC:DD:EE:FF
g1-dancer speaker connected
```

Select the Bluetooth speaker as the PC's default audio output in the desktop sound settings (or with `wpctl`/`pactl`). G1 Dancer uses the first installed player among `mpv`, `ffplay`, `cvlc`, and `mpg123`; set `audio_player` in the config to pin one. Pairing is retained by BlueZ and does not require internet access.

## Run offline and control from another computer

Connect the controller computer to the development PC's hotspot. The development PC is the hotspot gateway at `10.42.0.1`; its separate Ethernet interface remains connected to the G1. Start the service and address it as follows:

```bash
# On the development PC
g1-dancer serve

# On the controller computer (copy this project/install the CLI first)
g1-dancer remote --url http://10.42.0.1:8787 add-mp3 clap-wave song.mp3
g1-dancer remote --url http://10.42.0.1:8787 play clap-wave --yes
```

The remote CLI intentionally has only `add-mp3` and `play`. The named dance must already exist under `~/.local/share/g1-dancer/routines` on the development PC; a remote user cannot upload or edit dance definitions. Adding another MP3 to the same dance replaces its previous MP3.

Allow TCP port 8787 only on the private Wi-Fi interface in the PC firewall. The API has no login or token and uses plain HTTP, so every device that can reach this port can operate it. Keep the hotspot private and use a firewall, VPN, or authenticated TLS reverse proxy if the network is not fully trusted. Dance playback still requires an explicit safety-confirmation header.

To start at login without root, install the included user service:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/g1-dancer.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now g1-dancer.service
```

## Add routines

Create `~/.local/share/g1-dancer/routines/my-dance.json`:

```json
{
  "id": "my-dance",
  "name": "My Dance",
  "description": "A locally authored routine",
  "audio": null,
  "steps": [
    {"at": 0.0, "type": "arm_action", "action_id": 17},
    {"at": 4.0, "type": "loco", "method": "WaveHand", "args": []},
    {"at": 8.0, "type": "arm_action", "action_id": 99}
  ]
}
```

Times are seconds from the shared audio/motion start. Files are re-read whenever routines are listed or played. The validator accepts only explicit arm action IDs and an allow-list of safe high-level locomotion methods; it never executes commands from routine JSON. Uploading an MP3 stores it as `<routine-id>.mp3` and atomically updates the routine's `audio` field.

Run checks with:

```bash
python3 -m unittest discover -v
python3 -m compileall -q g1_dancer tests
```

## API

Authenticated endpoints are `GET /api/health`, `GET /api/routines`, `GET /api/status`, `PUT /api/routines/{id}/audio` (raw MP3 body), `DELETE /api/routines/{id}/audio`, `POST /api/routines/{id}/play`, `POST /api/routines/{id}/music`, `POST /api/pause`, `POST /api/resume`, `POST /api/reset`, and `POST /api/stop`. Dance playback requires `X-G1-Safety-Confirmed: YES`; music-only playback does not move or initialize the robot.
