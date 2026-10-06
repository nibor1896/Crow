[← README](../../README.md) · [Docs index](../README.md) · [Phone (remote)](remote.md)

# Phone over Tailscale (HTTPS)

`https://<pc>.<tailnet>.ts.net/` — the phone mirror from anywhere, and the phone's microphone
(#249 stage 5, #290). Crow never runs a Tailscale command that changes anything; it reads the
state and the Remote dialog shows the next step.

## 0. The installer route

The installers read where this machine stands (`tailscale status --json`, `tailscale serve status
--json`) and print only the steps still missing, in the order below. Neither runs sudo or elevates.

| OS | command |
|---|---|
| Linux | `bash install.sh --tailscale` · no checkout: `curl -fsSL https://raw.githubusercontent.com/nibor1896/Crow/main/install.sh \| bash -s -- --tailscale` |
| Windows | `&([scriptblock]::Create((irm https://raw.githubusercontent.com/nibor1896/Crow/main/install.ps1))) -Tailscale` — prints the steps and exits, installs nothing |

| downloads | |
|---|---|
| all platforms | [tailscale.com/download](https://tailscale.com/download) |
| iPhone | [App Store](https://apps.apple.com/app/tailscale/id1470499037) |
| Android | [Google Play](https://play.google.com/store/apps/details?id=com.tailscale.ipn) |
| Linux | [kb/1031](https://tailscale.com/kb/1031/install-linux) |
| Windows | [kb/1022](https://tailscale.com/kb/1022/install-windows) · `winget install --id Tailscale.Tailscale -e` (id from [winget-pkgs](https://github.com/microsoft/winget-pkgs/tree/master/manifests/t/Tailscale/Tailscale); kb/1022 names only the .exe/.msi) |

Sections 2–5 are the same steps by hand.

## 1. What and why

| | |
|---|---|
| reach | phone on mobile data or any Wi-Fi, no static IP, no router port forwarding |
| HTTPS | the phone's 🎤 needs a secure context; `getUserMedia` does not exist on plain `http://<LAN IP>` ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)) |
| who can connect | only devices logged in to your tailnet, and then only a paired phone (QR + desktop Allow) |
| cost | Personal plan: "Free forever", up to 6 users, unlimited user devices, non-commercial use only — [tailscale.com/pricing](https://tailscale.com/pricing) |
| privacy | enabling HTTPS publishes the machine name and tailnet DNS name in the public Certificate Transparency log — [kb/1153](https://tailscale.com/kb/1153/enabling-https). Rename the PC first if its name says too much |

## 2. Account and phone app

| step | |
|---|---|
| iPhone | [App Store → **Tailscale**](https://apps.apple.com/app/tailscale/id1470499037) → log in |
| Android | [Play Store → **Tailscale**](https://play.google.com/store/apps/details?id=com.tailscale.ipn) → log in |
| account | the **same** account on the phone and the PC — a second account is a second tailnet |

## 3. Install on the PC

| OS | install | source |
|---|---|---|
| Arch / Omarchy | `sudo pacman -S tailscale` | Arch `extra` repo (checked: `tailscale 1.102.3-1` on robin's PC) |
| Debian / Ubuntu / Fedora | `curl -fsSL https://tailscale.com/install.sh \| sh` | [kb/1031](https://tailscale.com/kb/1031/install-linux) |
| Debian / Ubuntu, by hand | the per-release `curl … noarmor.gpg` / `… tailscale-keyring.list` lines, then `sudo apt-get update && sudo apt-get install tailscale` | [pkgs.tailscale.com/stable](https://pkgs.tailscale.com/stable/) |
| Fedora, by hand | `sudo dnf config-manager --add-repo https://pkgs.tailscale.com/stable/fedora/tailscale.repo` then `sudo dnf install tailscale` | [pkgs.tailscale.com/stable](https://pkgs.tailscale.com/stable/). Fedora 41+ ships dnf5, whose `config-manager` syntax differs — **not verified** |
| Windows | the `.exe` installer from [tailscale.com/download](https://tailscale.com/download/windows), or `winget install --id Tailscale.Tailscale -e`; then tray icon → **Log in** | [kb/1022](https://tailscale.com/kb/1022/install-windows); winget id: [winget-pkgs](https://github.com/microsoft/winget-pkgs/tree/master/manifests/t/Tailscale/Tailscale) |

Start and log in (Linux):

```bash
sudo systemctl enable --now tailscaled   # autostart; pkgs.tailscale.com/stable
sudo tailscale up                        # prints a login URL -> browser; kb/1031
tailscale status                         # the PC and the phone are listed
```

Windows: Tailscale runs as the Windows service `Tailscale` with start type **Automatic**, so it starts with the
machine (checked 2026-10-06 with `Get-Service Tailscale` on robin's PC, Tailscale 1.102.4; kb/1022 does not say).
The serve command in section 5 runs in a normal PowerShell, without elevation (same day).

## 4. Admin console

| step | where | check |
|---|---|---|
| MagicDNS on | [DNS page](https://login.tailscale.com/admin/dns) — [kb/1081](https://tailscale.com/kb/1081/magicdns) | `tailscale status --json` → `MagicDNSSuffix` is `<tailnet>.ts.net` |
| HTTPS on | same page → **HTTPS Certificates** → **Enable HTTPS**, acknowledge the public ledger — [kb/1153](https://tailscale.com/kb/1153/enabling-https) | `tailscale status --json` → `CertDomains` lists `<pc>.<tailnet>.ts.net` |

```bash
tailscale status --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['Self']['DNSName'], d['CertDomains'])"
```

## 5. The one-time serve command

```bash
sudo tailscale serve --bg --https=443 http://127.0.0.1:8765
```

| | |
|---|---|
| what | `https://<pc>.<tailnet>.ts.net/` → Crow's loopback listener; tailnet only (not Funnel) |
| `8765` | `remote_port`; use yours if you changed it — the Remote dialog prints the exact line with a copy button |
| persistence | `--bg` keeps it until you turn it off, across reboots — [kb/1242](https://tailscale.com/kb/1242/tailscale-serve) |
| certificate | provisioned and renewed automatically by Serve — [kb/1080](https://tailscale.com/kb/1080/cli) |
| check | `tailscale serve status` lists `https://<pc>.<tailnet>.ts.net` with `proxy http://127.0.0.1:8765` (exact layout **not verified**) |
| without sudo (optional) | `sudo tailscale set --operator=$USER` once — lets your user run `tailscale serve` — [kb/1080](https://tailscale.com/kb/1080/cli). Crow does not need it: it only reads |

## 6. In Crow

| step | |
|---|---|
| 1 | `/remote on` (or the phone icon). Crow listens on the LAN address **and** `127.0.0.1:8765` while Tailscale is up |
| 2 | Remote dialog → Network → **HTTPS · `<pc>.<tailnet>.ts.net`**. The status line must say `ready` |
| 3 | phone: Tailscale on → scan the QR → **Allow** on the desktop |
| 4 | Safari → Share → **Add to Home Screen** (a separate tile from the LAN one) |

Two origins, two pairings: a phone paired on `http://<LAN IP>:8765` pairs once more on the ts.net
address. Use the ts.net address at home too, and one pairing covers both.

## 7. Checks

| check | expected |
|---|---|
| phone: Wi-Fi **off**, mobile data, Tailscale on → open the home-screen tile | the session mirrors |
| send / Stop / Approve a card | all work, the desktop shows the same |
| 🎤 → speak → 🎤 | text in the phone's input within a few seconds, not sent |
| `ss -ltnp \| grep 8765` | only `<LAN IP>:8765` and `127.0.0.1:8765`; never `0.0.0.0:8765`, never `100.x:8765` |
| `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/` | `421` — the loopback takes only the ts.net Host |

## 8. Troubleshooting

The Remote dialog's status line for the HTTPS choice, and the fix:

| dialog says | fix |
|---|---|
| Tailscale is not installed | section 3, or `install.sh --tailscale` / `install.ps1 -Tailscale` |
| Tailscale is installed but not connected | `sudo systemctl enable --now tailscaled`, `sudo tailscale up` |
| HTTPS certificates are off for this tailnet | section 4, then reopen the dialog |
| one-time setup … `sudo tailscale serve …` | run it (section 5), reopen the dialog |
| Tailscale Funnel is on for …:443 | `sudo tailscale funnel --https=443 off` — Funnel would make the address public; Crow refuses to serve it |
| ready | — |

| symptom | fix |
|---|---|
| phone: page does not load, device offline | open the Tailscale app, VPN toggle on; `tailscale status` on the PC lists the phone |
| phone: Safari "cannot open the page because the server could not be found" | the phone's Tailscale is not connected, and the `ts.net` name only resolves with it on: Tailscale app → toggle **Connected**, allow the VPN profile the first time; `tailscale status` on the PC must show the phone without `offline` (seen 2026-09-24) |
| phone: login.tailscale.com "Error 403 — user is not authorized to view this auth request" | the login link met a browser signed in to another account, or a stale link: Tailscale app → account → **Log out**; in Safari open login.tailscale.com and sign out; app → **Log in** with the **same provider and account as on the PC** (seen 2026-09-24, Safari and Chrome) |
| phone: HTTPS address paired, LAN tile asks to pair again (or the reverse) | expected: `http://<LAN-IP>:8765` and `https://<pc>.<tailnet>.ts.net` are two origins with their own cookie; pair once on each, or use only the HTTPS one |
| certificate warning / error | HTTPS on in the console? `CertDomains` set? the first request after `serve` may take a few seconds while the certificate is fetched — **not verified** |
| page loads, 421 | the address is not the ts.net name (e.g. the 100.x IP) — use `https://<pc>.<tailnet>.ts.net/` |
| 🎤 "the microphone did not open (NotAllowedError)" | iOS: Settings → Apps → Safari → Microphone → Ask/Allow; or `aA` in the address bar → Website Settings → Microphone |
| 🎤 "dictation needs faster-whisper" | `bash install.sh --voice` on the PC |
| 🎤 shows the keyboard hint | the page is the plain-HTTP LAN address — switch to the HTTPS tile |
| ufw on and the HTTPS address hangs | `sudo ufw allow in on tailscale0` — **not verified**: tailscaled normally accepts its own interface |
| the LAN IP changed (DHCP) | irrelevant for the ts.net address; its name and `100.x` address stay fixed — [kb/1015](https://tailscale.com/kb/1015/100.x-addresses) |

## 9. Undo

```bash
sudo tailscale serve --https=443 off     # this one mapping — kb/1242: add "off" to the command
sudo tailscale serve reset               # every serve mapping — kb/1242
sudo tailscale down                      # disconnect this PC — kb/1080
sudo systemctl disable --now tailscaled  # no autostart
sudo pacman -Rns tailscale               # Arch; Debian/Ubuntu: sudo apt-get remove tailscale; Fedora: sudo dnf remove tailscale
```

Then in Crow: Remote dialog → the LAN address; `/remote forget <name>` for the ts.net pairing.
Remove the machine in the admin console's Machines page if it should leave the tailnet.
