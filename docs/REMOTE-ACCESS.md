# Remote access — viewing the dashboard from your phone (Tailscale)

The daytrade bot and dashboard run **on your Mac**. Tailscale builds a small
private network between your own devices so your phone can reach the dashboard
directly — **nothing is exposed to the public internet**.

Paper / simulation only. The dashboard is read-only: no real trading, no
wallets, no orders, no money movement. Tailscale only changes *who can view*
the page; it changes nothing about what the bot does.

## One-time setup

1. **Install Tailscale on the Mac**

   ```
   brew install --cask tailscale
   ```

   Then open the Tailscale app and sign in (Google / Microsoft / email).

2. **Install Tailscale on your phone** — App Store (iOS) or Play Store
   (Android) — and sign in with the **same account**.

3. **Find the Mac's Tailscale address**

   ```
   tailscale ip -4
   ```

   This prints a `100.x.y.z` address. That is your Mac's private address on
   the Tailscale network.

## Every time you want remote access

1. **Start the bot** (if it is not already running):

   ```
   PYTHONPATH=src python3 -m daytrade learn --days 30 --interval 60 --real-data
   ```

2. **Start the dashboard** with the helper script:

   ```
   ./scripts/run-dashboard.sh
   ```

   It asks for a password, binds `0.0.0.0:8000`, and prints the Tailscale URL.

3. **On your phone**, with Tailscale connected, open:

   ```
   http://100.x.y.z:8000
   ```

   Enter any username and the password you chose.

## Notes

- The dashboard is only online while your Mac is awake and the script is
  running. For always-on access, the bot + dashboard need to run on a server
  instead — see the hosting options discussion.
- The password is set via the `DASHBOARD_PASSWORD` environment variable. With
  no password set, the dashboard runs **open** (fine for `localhost`, not for
  remote access).
- Keep `--host 127.0.0.1` (the default `daytrade dashboard`) when you only use
  the dashboard locally; `0.0.0.0` is only needed for Tailscale/remote access.
