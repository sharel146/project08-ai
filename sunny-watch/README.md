# Sunny Watch (Amazfit GTR 3 Pro)

A Zepp OS mini-app that lets you talk to **Sunny** from your wrist: tap a quick
message, and Sunny's reply shows on the watch.

```
[ GTR 3 Pro ] --BLE--> [ Zepp app on your phone ] --HTTP--> [ Sunny on your PC ]
   tap a message          app-side/index.js (fetch)            POST /chat
        ^------------------------ reply --------------------------------'
```

## Honest limitations (read first)

- The GTR 3 Pro runs **Zepp OS 2.x**, not Wear OS. This is a *mini-app*, not an
  APK, and it can't stream audio or do free-form typing.
- **No keyboard:** input is **tap-to-send quick messages** (edit the list in
  `page/index.js`). That's the realistic way to "talk" on this watch.
- The watch has no internet of its own — all network goes through the **Zepp app
  on your phone** (the `app-side` service), which must be able to reach Sunny.

## Prerequisites

1. **Sunny's HTTP API running** (see the `sunny/` folder):
   ```bash
   cd ../sunny
   # in .env, set SUNNY_HTTP_TOKEN=some-long-secret
   ./run.sh serve-http      # or: python -m sunny.main serve-http
   ```
   Note the port (default 8765) and your PC's LAN IP. To reach Sunny from
   anywhere (not just home Wi-Fi), put your PC and phone on a
   [Tailscale](https://tailscale.com) network and use the PC's Tailscale IP.

2. **Zepp OS toolchain:**
   ```bash
   npm install -g @zeppos/zeus-cli
   ```

## Build & install (the reliable path)

Because the Bluetooth messaging layer (`shared/message.js`) and the exact device
target metadata are SDK-version specific, generate a clean base with the CLI and
drop these app files in:

1. **Scaffold a base project** and pick a JavaScript template that includes
   phone↔watch communication / fetch:
   ```bash
   zeus create sunny-watch-build
   ```
   This generates `app.js`, `shared/message.js`, an `assets/` icon, and a valid
   `app.json` with device targets.

2. **Copy these files into the generated project**, overwriting where they
   exist:
   - `page/index.js`
   - `app-side/index.js`
   - merge the `module`, `permissions`, and `gtr-3-pro` target from this
     `app.json` into the generated one (keep the generated `appId` and the
     `platforms`/`deviceSource` the CLI produced for your account).
   - `app.js` here matches the template's pattern; keep the generated one if it
     differs.

3. **Set your server details** in `app-side/index.js`:
   - `SUNNY_URL` → `http://<your-PC-IP>:8765/chat`
   - `SUNNY_TOKEN` → the same value as `SUNNY_HTTP_TOKEN` in Sunny's `.env`

4. **Put the watch in Developer Mode:** Zepp app → Profile → your GTR 3 Pro →
   scroll down → enable **Developer Mode** (phone and PC on the same network).

5. **Run it on the watch:**
   ```bash
   zeus dev        # live-reload to the watch over the bridge
   # or
   zeus preview    # produces a QR code; scan it in the Zepp app to install
   ```
   For a permanent install, `zeus build` produces a `.zab`/`.zpk` you can
   side-load via the Zepp app.

## Files in this folder

- `page/index.js` — the watch UI (quick messages + reply display).
- `app-side/index.js` — the phone-side service that calls Sunny's API.
- `app.js` — sets up the messaging bridge.
- `app.json` — app + GTR 3 Pro target (reference; merge with the generated one).

## Customizing what you can say

Edit `QUICK_MESSAGES` in `page/index.js`. Anything you put there is sent
verbatim to Sunny, so "Turn on the desk lamp", "Start my evening routine", etc.
all work as long as Sunny has a matching capability.
