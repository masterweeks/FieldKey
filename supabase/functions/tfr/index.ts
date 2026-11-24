// FieldKey relay for FAA TFRs and NWS fire-weather zones. tfr.faa.gov doesn't allow browser calls from
// other sites (no CORS), and QGIS needs NWS fire-weather alerts as one file of shapes. This function only
// reads fixed, public FAA and NWS addresses, holds no keys or secrets, and touches no data, so it runs
// without login (verify_jwt off).
//
//   GET /functions/v1/tfr?bbox=W,S,E,N   active TFR shapes in that box (GeoJSON)
//   GET /functions/v1/tfr?id=6/2547      one TFR's details: times, floor/ceiling, NOTAM text
//   GET /functions/v1/tfr?fire=1         active Red Flag Warnings and Fire Weather Watches as zone shapes
//   add &qgis=1 to a list to get one blank placeholder first (property "placeholder": 1), so QGIS
//   knows the shape type and fields even when nothing is active; FieldKey's QGIS layers filter it out.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const FAA = "https://tfr.faa.gov";
const WFS = FAA + "/geoserver/TFR/ows?service=WFS&version=1.1.0&request=GetFeature&typeName=TFR:V_TFR_LOC" +
  "&outputFormat=application/json&srsname=EPSG:4326&bbox=";
const NWS = "https://api.weather.gov";
const UA = "FieldKey relay (https://github.com/masterweeks/FieldKey)";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type",
};

function reply(body: unknown, status = 200, maxAge = 300) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS, "Content-Type": "application/json", "Cache-Control": `public, max-age=${maxAge}` },
  });
}

async function get(url: string, ms = 20000, accept = "application/json") {
  const r = await fetch(url, { signal: AbortSignal.timeout(ms), headers: { "User-Agent": UA, Accept: accept } });
  if (!r.ok) throw new Error(`${new URL(url).host} answered ${r.status}`);
  return r;
}

type Feature = { type: "Feature"; id?: number | string; geometry: unknown; properties: Record<string, unknown> };
const collection = (features: Feature[]) => ({ type: "FeatureCollection", features });
const BLANK = { type: "Polygon", coordinates: [[[0, 0], [0.0001, 0], [0.0001, 0.0001], [0, 0]]] };
function placeholder(fields: string[]): Feature {
  const properties: Record<string, unknown> = { placeholder: 1 };
  for (const f of fields) properties[f] = "";
  return { type: "Feature", id: 0, geometry: BLANK, properties };
}

// The shape service keeps some expired TFRs, so only shapes whose NOTAM is on the current list are returned.
const TFR_FIELDS = ["id", "type", "title", "state", "facility", "modified"];
async function shapes(bbox: string) {
  const [list, geo] = await Promise.all([
    get(FAA + "/tfrapi/getTfrList").then((r) => r.json()),
    get(WFS + bbox + ",EPSG:4326").then((r) => r.json()),
  ]);
  const active = new Map<string, Record<string, string>>();
  for (const t of list || []) if (t && t.notam_id) active.set(String(t.notam_id), t);
  const features: Feature[] = [];
  for (const f of geo.features || []) {
    const p = f.properties || {};
    const id = String(p.NOTAM_KEY || "").split("-")[0];
    const t = active.get(id);
    if (!t || !f.geometry) continue;
    features.push({
      type: "Feature",
      id: Number(p.GID) || undefined,   // one TFR can have several shapes; the app de-duplicates by this
      geometry: f.geometry,
      properties: {
        id, type: t.type || p.LEGAL || "", title: p.TITLE || t.description || "", state: t.state || p.STATE || "",
        facility: t.facility || p.CNS_LOCATION_ID || "", modified: t.mod_date || "",
      },
    });
  }
  return features;
}

const tag = (xml: string, name: string) => {
  const m = xml.match(new RegExp(`<${name}>([\\s\\S]*?)</${name}>`));
  return m ? m[1].replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, "&").trim() : "";
};

async function details(id: string) {
  const xml = await (await get(`${FAA}/download/detail_${id.replace("/", "_")}.xml`)).text();
  const alt = (k: string) => ({ val: tag(xml, `valDistVer${k}`), uom: tag(xml, `uomDistVer${k}`), code: tag(xml, `codeDistVer${k}`) });
  return {
    id,
    city: tag(xml, "txtNameCity"), state: tag(xml, "txtNameUSState"),
    effective: tag(xml, "dateEffective"), expires: tag(xml, "dateExpire"), timeZone: tag(xml, "codeTimeZone"),
    lower: alt("Lower"), upper: alt("Upper"),
    text: tag(xml, "txtDescrTraditional"),
    link: `${FAA}/tfr3/?page=detail_${id.replace("/", "_")}`,
  };
}

// Red Flag Warnings / Fire Weather Watches. NWS alerts name fire-weather zones instead of carrying shapes,
// so each zone's shape is fetched (and kept for a day: zones rarely change).
const FIRE_FIELDS = ["event", "headline", "ends", "area", "zone", "zoneName"];
const zoneCache = new Map<string, { geometry: unknown; name: string; at: number }>();
async function zone(url: string) {
  const hit = zoneCache.get(url);
  if (hit && Date.now() - hit.at < 86400000) return hit;
  const z = await (await get(url, 15000, "application/geo+json")).json();
  if (!z || !z.geometry) return null;
  const v = { geometry: z.geometry, name: (z.properties && z.properties.name) || "", at: Date.now() };
  zoneCache.set(url, v);
  return v;
}
async function fireWeather() {
  const a = await (await get(NWS + "/alerts/active?event=" + encodeURIComponent("Red Flag Warning,Fire Weather Watch"), 20000,
    "application/geo+json")).json();
  const features: Feature[] = [], jobs: { p: Record<string, string>; url: string }[] = [];
  for (const f of a.features || []) {
    const p = f.properties || {};
    if (f.geometry) {
      features.push({ type: "Feature", id: p.id, geometry: f.geometry,
        properties: { event: p.event, headline: p.headline || "", ends: p.ends || p.expires || "", area: p.areaDesc || "", zone: "", zoneName: "" } });
      continue;
    }
    for (const url of p.affectedZones || []) if (/\/zones\/(fire|forecast|county)\/[A-Z]{2}[CZ]\d{3}$/.test(url)) jobs.push({ p, url });
  }
  for (let i = 0; i < jobs.length; i += 8) {          // eight zone requests at a time
    const got = await Promise.all(jobs.slice(i, i + 8).map((j) => zone(j.url).catch(() => null)));
    got.forEach((z, k) => {
      const { p, url } = jobs[i + k];
      if (z) features.push({ type: "Feature", id: p.id + "|" + url.split("/").pop(), geometry: z.geometry,
        properties: { event: p.event, headline: p.headline || "", ends: p.ends || p.expires || "", area: p.areaDesc || "",
          zone: url.split("/").pop(), zoneName: z.name } });
    });
  }
  return features;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (req.method !== "GET") return reply({ error: "GET only" }, 405, 0);
  const q = new URL(req.url).searchParams;
  const forQgis = q.get("qgis") === "1";
  try {
    const id = q.get("id");
    if (id) {
      if (!/^\d{1,2}\/\d{1,5}$/.test(id)) return reply({ error: "Bad TFR id" }, 400, 0);
      return reply(await details(id), 200, 600);
    }
    if (q.get("fire") === "1") {
      const f = await fireWeather();
      return reply(collection(forQgis ? [placeholder(FIRE_FIELDS), ...f] : f), 200, 600);
    }
    const b = (q.get("bbox") || "").split(",").map(Number);
    const ok = b.length === 4 && b.every(Number.isFinite) && b[0] >= -180 && b[2] <= 180 && b[1] >= -90 && b[3] <= 90 &&
      b[0] < b[2] && b[1] < b[3];
    if (!ok) return reply({ error: "bbox must be W,S,E,N in degrees" }, 400, 0);
    const f = await shapes(b.map((v) => v.toFixed(4)).join(","));
    return reply(collection(forQgis ? [placeholder(TFR_FIELDS), ...f] : f));
  } catch (e) {
    return reply({ error: "Couldn't reach the FAA or NWS: " + (e instanceof Error ? e.message : String(e)) }, 502, 0);
  }
});
