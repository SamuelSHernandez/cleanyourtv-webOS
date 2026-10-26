# Setting up an LG TV, step by step

This is the full path from a stock LG TV to CYTV Home, as it was done on an LG 50UQ7570PUJ (webOS 22, firmware
04.60.91), with the problems met on the way and their fixes. Allow about 20 minutes. Nothing here roots the TV,
changes its firmware or turns anything of LG's off; `cytv-webos restore` undoes it.

## 1. An LG developer account (free)

Create an account at [webostv.developer.lge.com](https://webostv.developer.lge.com) (Sign in, then Create
account). It is what lets the TV run apps you install yourself. No payment, no app submission.

## 2. Developer Mode on the TV

1. On the TV, open the **LG Content Store**, search for **Developer Mode** and install it.
2. Open Developer Mode and sign in with the developer account.
3. Turn **Dev Mode Status** on. The TV restarts.
4. Open Developer Mode again and turn **Key Server** on. It shows a **passphrase** (six characters) and the
   session's remaining time.

**The session expires.** The Developer Mode app shows the time left and has an **Extend** button: use it before
the time runs out. When a session expires, the TV removes the apps you installed (CYTV Home included). LG Home
is untouched. Turn Dev Mode back on and run `cytv-webos install --device tv` again. Your theme is remembered.

## 3. The computer

- Python 3.9 or newer (macOS and Linux have it).
- Node.js 18 or newer, then LG's command-line tool:
  ```sh
  npm install -g @webos-tools/cli@3.2.6
  ```
- This repository (`git clone ...`).

## 4. The TV's address

Find it in the TV's network settings, or in your router's list of devices. One way that works on macOS and
Linux once the TV has been on the network: `arp -an` lists addresses next to their MAC addresses. The TV's MAC
is in its network settings. Use the TV's address where `<tv ip>` appears below.

## 5. Let the computer talk to Developer Mode

```sh
ares-setup-device -a tv -i "host=<tv ip>" -i "port=9922" -i "username=prisoner"
ares-novacom --device tv --getkey        # type the passphrase the Developer Mode app shows
```

Then turn **Key Server** off on the TV; the key is now on the computer (`~/.ssh/tv_webos`).

**If `--getkey` could not ask you for the passphrase.** This happens when the command runs somewhere that cannot
take typed input, such as an assistant's shell. The key file arrives, but the CLI does not record the passphrase
or link the key to the device. Every later command then fails with
`All configured authentication methods failed`. Fix both with:

```sh
ares-setup-device -m tv -i "passphrase=<passphrase>" -i "privateKey=tv_webos"
ares-device --device tv --system-info    # should print modelName, sdkVersion, firmwareVersion
```

Type the passphrase yourself; do not paste it into a chat or a file.

## 6. Install CYTV Home

```sh
webos/cytv-webos setup   --device tv --host <tv ip>
webos/cytv-webos check   --device tv              # read-only: model, firmware, profile, problems
webos/cytv-webos pair    --device tv              # a prompt appears on the TV: choose Accept
webos/cytv-webos sync    --device tv              # your apps, their icons, your HDMI inputs
webos/cytv-webos install --device tv              # installs, launches, and checks each step
```

`install` prints each stage:

- `installed`, `launched` and `running` should say yes;
- `foreground` says yes once the app is in front (it asks again for a few seconds);
- `ready` is the question only you can answer: look at the TV.

```sh
webos/cytv-webos confirm-ready --device tv --answer yes     # once it works on screen
```

## 7. Make it yours

Your own theme lives in a folder outside the repository, for example `~/cytv-my-home/config.json`. Only three
apps on Home, everything else behind App library:

```json
{
  "dock_apps": ["spotify-beehive", "youtube.leanback.v4", "com.wbd.stream"],
  "dock_only": true,
  "columns": 3
}
```

```sh
webos/cytv-webos install --device tv --theme ~/cytv-my-home     # remembered for later installs
```

App ids come from `sync`, in `~/.cleanyourtv-webos/tv/inventory/inventory.json`. The full list of keys is in
[`../themes/README.md`](../themes/README.md). On the TV:

- hold OK on a tile to Move it or take it off Home;
- **App library** adds an app back;
- hold OK on Settings for Launcher settings.

## 8. Making it the app you land on

webOS does not let an app replace the Home button: without root, Home always opens LG's home screen. These
LG features make CYTV Home the place you land, with nothing running on your computer:

- **Quick Access.** Press and hold a number key on the remote (for example **1**). The TV offers to assign an
  app to it: choose **CYTV Home**. From then on, holding that key opens CYTV Home. It is LG's own feature, so
  it survives restarts and needs nothing else running.
- **Home Auto Launch off.** So the TV does not open LG's home screen by itself when it turns on. On webOS 22 it
  is under Settings, General, System, Additional Settings, Home Settings. Names vary a little between models.
- **Casting** (YouTube, AirPlay, Screen Share) is LG's and keeps working as before. CYTV Home only shows tiles;
  it turns nothing off.

The `home` commands in this tool (an external watcher that opens CYTV Home when LG Home appears) need a computer
running on the same network. They are experimental and off unless you enable them: see
[`recovery.md`](recovery.md).

## 9. When something is off

| What you see | What to do |
|---|---|
| `All configured authentication methods failed` | Step 5: passphrase or key not linked |
| `check` says SSAP not paired | `pair`, and accept the prompt on the TV |
| A black screen when CYTV Home opens | An old build: install again (fixed in this version; see `compatibility.md`, assumption 4) |
| An app installed after `sync` is missing | `sync`, then `install` |
| CYTV Home vanished from the TV | Developer Mode expired: step 2, then `install` |
| Anything uncertain | `webos/cytv-webos status --device tv`; to remove it all, `webos/cytv-webos restore --device tv` |
| A picture of the launcher for a bug report | `webos/cytv-webos screenshot --device tv` (from the TV's own engine) |
