// FieldKey canopy proxy (Supabase Edge Function, Deno)
//
// Serves Meta/WRI 1 m canopy-height COG tiles to the browser with the CORS and
// HTTP Range support that geotiff.js needs. The Meta S3 bucket is publicly
// readable but sends no CORS headers, so a browser can't read it directly. This
// function fetches the requested tile server-side and re-serves it with the
// right headers, streaming the bytes straight through.
//
// Deploy once, with JWT verification OFF so the map can call it without a token:
//
//     supabase functions deploy canopy --no-verify-jwt
//
// Endpoint:  https://<your-project-ref>.supabase.co/functions/v1/canopy
// Then paste that URL into FieldKey → Settings → "Canopy proxy URL".

const BASE =
  "https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float/chm";

const CORS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
  "Access-Control-Allow-Headers": "range, content-type",
  "Access-Control-Expose-Headers":
    "content-range, content-length, accept-ranges, content-type, etag",
  "Access-Control-Max-Age": "86400",
};

Deno.serve(async (req: Request) => {
  // CORS preflight (geotiff.js range reads normally skip this, but be safe).
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS });
  }
  if (req.method !== "GET" && req.method !== "HEAD") {
    return new Response("Method not allowed", { status: 405, headers: CORS });
  }

  // Accept ONLY a quadkey (digits 0-3). This keeps the function locked to the
  // Meta canopy bucket — it can't be turned into an open proxy for arbitrary URLs.
  const qk = new URL(req.url).searchParams.get("qk") ?? "";
  if (!/^[0-3]{1,24}$/.test(qk)) {
    return new Response("Missing or invalid 'qk' (canopy quadkey).", {
      status: 400,
      headers: CORS,
    });
  }

  const range = req.headers.get("range");
  const upstreamHeaders: HeadersInit = range ? { Range: range } : {};

  let upstream: Response;
  try {
    upstream = await fetch(`${BASE}/${qk}.tif`, {
      method: req.method,
      headers: upstreamHeaders,
    });
  } catch {
    return new Response("Upstream fetch failed.", { status: 502, headers: CORS });
  }

  // Pass through the pieces geotiff.js relies on (status 200 / 206 / 404 too).
  const headers = new Headers(CORS);
  for (
    const h of [
      "content-type",
      "content-length",
      "content-range",
      "accept-ranges",
      "etag",
      "last-modified",
    ]
  ) {
    const v = upstream.headers.get(h);
    if (v) headers.set(h, v);
  }
  if (!headers.has("content-type")) headers.set("content-type", "image/tiff");
  // Canopy tiles never change — let the browser/CDN cache them hard.
  headers.set("cache-control", "public, max-age=604800, immutable");

  return new Response(req.method === "HEAD" ? null : upstream.body, {
    status: upstream.status,
    headers,
  });
});
