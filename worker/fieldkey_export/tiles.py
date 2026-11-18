"""Web-Mercator tile maths, tile planning and package size estimates.

The same rules are implemented in FieldKey (index.html, "export estimate") so the phone can
show the size before a job is queued; tests/fixtures/export_estimate.json keeps the two in step.

Planning: for each zoom level, if the whole export area needs no more than FULL_AREA_TILES
tiles, take all of them (good overview at low zoom). Above that, take only the tiles that touch
a buffered box around each feature, so a long spread-out mission doesn't pull in every tile
of the empty land between sites.
"""
import math

WORLD = 20037508.342789244          # half the width of the EPSG:3857 world, metres
MAX_LAT = 85.0511287798066
FULL_AREA_TILES = 64                # per zoom: take the whole area while it's at most this many tiles
PLAN_TILE_LIMIT = 250000            # stop planning past this (way over any cap anyway)
BASE_BYTES = 480 * 1024             # empty GeoPackage + metadata tables + embedded QGIS styles (~0.3 MB)
BYTES_PER_FEATURE = 1000            # attributes + geometry + spatial index, roughly


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lonlat_to_tile(lon, lat, z):
    n = 1 << z
    lat = clamp(lat, -MAX_LAT, MAX_LAT)
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return clamp(x, 0, n - 1), clamp(y, 0, n - 1)


def tile_range(bbox, z):
    """(x0, y0, x1, y1) inclusive for a (west, south, east, north) box."""
    w, s, e, n = bbox
    x0, y0 = lonlat_to_tile(w, n, z)
    x1, y1 = lonlat_to_tile(e, s, z)
    return x0, y0, x1, y1


def buffer_bbox(bbox, metres):
    """Grow a lon/lat box by about `metres` on every side."""
    w, s, e, n = bbox
    mid = math.radians(clamp((s + n) / 2.0, -89.0, 89.0))
    dlat = metres / 111320.0
    dlon = metres / (111320.0 * max(math.cos(mid), 0.01))
    return (max(w - dlon, -180.0), max(s - dlat, -MAX_LAT), min(e + dlon, 180.0), min(n + dlat, MAX_LAT))


def union_bbox(boxes):
    boxes = list(boxes)
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def plan_tiles(feature_boxes, min_zoom, max_zoom, limit=PLAN_TILE_LIMIT):
    """feature_boxes: buffered (w, s, e, n) boxes. Returns ({zoom: sorted [(x, y)]}, total, truncated)."""
    feature_boxes = [b for b in feature_boxes if b]
    area = union_bbox(feature_boxes)
    plan, total = {}, 0
    if area is None:
        return plan, 0, False
    for z in range(min_zoom, max_zoom + 1):
        x0, y0, x1, y1 = tile_range(area, z)
        if (x1 - x0 + 1) * (y1 - y0 + 1) <= FULL_AREA_TILES:
            tiles = {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
        else:
            tiles = set()
            for b in feature_boxes:
                a0, b0, a1, b1 = tile_range(b, z)
                for x in range(a0, a1 + 1):
                    for y in range(b0, b1 + 1):
                        tiles.add((x, y))
                if total + len(tiles) > limit:
                    break
        plan[z] = sorted(tiles)
        total += len(tiles)
        if total > limit:
            return plan, total, True
    return plan, total, False


def estimate_bytes(feature_count, tile_counts):
    """tile_counts: list of (tile count, average bytes per tile) for each basemap."""
    return BASE_BYTES + feature_count * BYTES_PER_FEATURE + sum(int(n * avg) for n, avg in tile_counts)


def tile_bounds_3857(x, y, z):
    size = 2 * WORLD / (1 << z)
    minx = -WORLD + x * size
    maxy = WORLD - y * size
    return minx, maxy - size, minx + size, maxy


def bbox_to_3857(bbox):
    w, s, e, n = bbox

    def fwd(lon, lat):
        lat = clamp(lat, -MAX_LAT, MAX_LAT)
        return lon * WORLD / 180.0, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * WORLD / math.pi

    x0, y0 = fwd(w, s)
    x1, y1 = fwd(e, n)
    return x0, y0, x1, y1
