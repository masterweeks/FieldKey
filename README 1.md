# FieldKey canopy proxy

A ~40-line Supabase Edge Function that unlocks the **measured 1-meter tree-canopy
data** in FieldKey's line-of-sight tool.

## Why this exists
FieldKey can fold real tree heights into a sightline so a line crossing a tree
stand reads as blocked. That data (the Meta/WRI 1 m canopy map) lives in a public
AWS bucket that a **browser can't read directly** — the bucket sends no CORS
headers, so the request is blocked. Without this proxy, FieldKey falls back to a
flat "typical tree height" you set by hand.

This function fetches the canopy tile **server-side** (where CORS doesn't apply)
and re-serves it with the headers a browser needs, including HTTP Range support so
the map reads only the few small byte-ranges it needs per sightline.

## What's here
```
supabase/functions/canopy/index.ts   the function
supabase/config.toml                 block that turns off the login-token check
```

## Deploy (one time, ~5 min)
1. Install the CLI and sign in:
   ```
   npm install -g supabase
   supabase login
   ```
2. Link to your project (create a free project at supabase.com first if needed):
   ```
   supabase link --project-ref <your-project-ref>
   ```
3. Copy the `supabase/functions/canopy/` folder into your project (this repo
   mirrors the expected layout), then deploy **without JWT verification** so the
   map can call it with no login token:
   ```
   supabase functions deploy canopy --no-verify-jwt
   ```
   Your endpoint is:
   ```
   https://<your-project-ref>.supabase.co/functions/v1/canopy
   ```

## Point FieldKey at it
FieldKey → **Settings → "Canopy proxy URL"** → paste the endpoint above → save.
Then open **Line of sight → Include tree canopy**. The panel should now read
**"with tree canopy (measured)"** instead of the "~N ft" assumption.

## Sanity check
```
curl -I "https://<your-project-ref>.supabase.co/functions/v1/canopy?qk=023010203"
```
Expect `HTTP/2 200`, `access-control-allow-origin: *`, and `accept-ranges: bytes`.
(Any real quadkey works; a 404 just means no canopy tile covers that quadkey.)

## Notes
- **Cost:** negligible. Tiles are cached (immutable), and each check reads only a
  few small ranges — comfortably inside Supabase's free tier.
- **Safety:** the function accepts only a quadkey (digits 0-3), so it can't be used
  to proxy arbitrary URLs.
- **Coverage:** trees only — buildings and structures aren't in the canopy data.
  Data © Meta / World Resources Institute, free for commercial use.
