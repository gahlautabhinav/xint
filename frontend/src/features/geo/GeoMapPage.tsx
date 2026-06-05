import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as L from "leaflet";
import { Clock, Loader2, MapPin, Search } from "lucide-react";

import { api } from "@/lib/api";
import type { GeoPoint } from "@/lib/types";
import "leaflet/dist/leaflet.css";
import "./geo.css";

const SOURCE_COLOR: Record<string, string> = {
  tweet_geo: "#00c2ff", // actual tagged post location
  profile: "#ff6b35", // claimed profile location
};

const CONFIDENCE_OPACITY: Record<string, number> = {
  high: 1,
  medium: 0.72,
  low: 0.45,
};

// CartoDB dark basemap — free, no API key.
const TILE_URL = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const TILE_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>';

function pinSize(followers: number): number {
  // sqrt scale so a 1M-follower account isn't 1000× a 1-follower one.
  return Math.max(11, Math.min(30, 11 + Math.sqrt(followers) / 12));
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}

function popupHtml(p: GeoPoint): string {
  const tz =
    p.timezone_utc_offset != null
      ? `<div class="geo-pop__row">UTC${p.timezone_utc_offset >= 0 ? "+" : ""}${p.timezone_utc_offset} (posting rhythm)</div>`
      : "";
  const place = p.geocoded_name ? escapeHtml(p.geocoded_name) : "";
  return `
    <div class="geo-pop">
      <a class="geo-pop__handle" href="/?q=${encodeURIComponent(p.username)}">@${escapeHtml(p.username)}</a>
      ${p.display_name ? `<div class="geo-pop__name">${escapeHtml(p.display_name)}</div>` : ""}
      <div class="geo-pop__loc">“${escapeHtml(p.location_text)}”</div>
      ${place ? `<div class="geo-pop__row geo-pop__resolved">${place}</div>` : ""}
      <div class="geo-pop__row">${p.followers_count.toLocaleString()} followers</div>
      ${tz}
      <div class="geo-pop__tags">
        <span class="geo-pop__tag" style="--c:${SOURCE_COLOR[p.source] ?? "#7d8187"}">${p.source === "tweet_geo" ? "post location" : "profile"}</span>
        <span class="geo-pop__tag geo-pop__tag--conf">${p.confidence}</span>
      </div>
    </div>`;
}

export function GeoMapPage() {
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const markersRef = useRef<Map<string, L.Marker>>(new Map());

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["geo-locations"],
    queryFn: () => api.getGeoLocations({ maxNew: 8 }),
    // Keep polling while the geocoder warms the cache, then stop.
    refetchInterval: (q) => ((q.state.data?.pending ?? 0) > 0 ? 3000 : false),
  });

  // ── Init map once ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [22, 5],
      zoom: 2,
      minZoom: 2,
      maxZoom: 18,
      worldCopyJump: true,
      attributionControl: true,
    });
    L.tileLayer(TILE_URL, { attribution: TILE_ATTR, maxZoom: 19 }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    // Container is sized by flex after mount — nudge Leaflet to recompute so
    // tiles don't render into a zero/half-height box (the classic grey map).
    const raf = requestAnimationFrame(() => map.invalidateSize());

    return () => {
      cancelAnimationFrame(raf);
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
      markersRef.current.clear();
    };
  }, []);

  // ── Render markers when points change ────────────────────────────────────
  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    layer.clearLayers();
    markersRef.current.clear();

    const points = data?.points ?? [];
    for (const p of points) {
      const size = pinSize(p.followers_count);
      const color = SOURCE_COLOR[p.source] ?? "#7d8187";
      const opacity = CONFIDENCE_OPACITY[p.confidence] ?? 0.6;
      const icon = L.divIcon({
        className: "geo-pin-wrap",
        html: `<span class="geo-pin" style="--c:${color};width:${size}px;height:${size}px;opacity:${opacity}"></span>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });
      const marker = L.marker([p.lat, p.lon], { icon, title: `@${p.username}` });
      marker.bindPopup(popupHtml(p), { className: "geo-popup" });
      marker.addTo(layer);
      markersRef.current.set(p.username, marker);
    }
  }, [data?.points]);

  const filteredPoints = useMemo(() => {
    const pts = data?.points ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return pts;
    return pts.filter(
      (p) =>
        p.username.toLowerCase().includes(q) ||
        (p.location_text ?? "").toLowerCase().includes(q),
    );
  }, [data?.points, search]);

  const flyTo = (p: GeoPoint) => {
    const map = mapRef.current;
    if (!map) return;
    map.flyTo([p.lat, p.lon], 8, { duration: 0.8 });
    markersRef.current.get(p.username)?.openPopup();
  };

  const points = data?.points ?? [];
  const tzOnly = data?.timezone_only ?? [];
  const pending = data?.pending ?? 0;

  return (
    <div className="geo-page">
      {/* Left panel */}
      <aside className="geo-panel">
        <div className="geo-panel__head">
          <span className="eyebrow">OSINT&nbsp;//&nbsp;GEO&nbsp;MAP</span>
          <p className="body-sm text-mute geo-panel__lead">
            Accounts pinned by geocoded profile location and tagged post
            locations. Coordinates resolved via OpenStreetMap Nominatim.
          </p>
        </div>

        <div className="geo-stats">
          <div className="geo-stat">
            <span className="geo-stat__num tabular">{points.length}</span>
            <span className="geo-stat__label">located</span>
          </div>
          <div className="geo-stat">
            <span className="geo-stat__num tabular">{data?.total_accounts ?? 0}</span>
            <span className="geo-stat__label">accounts</span>
          </div>
          <div className="geo-stat">
            <span className="geo-stat__num tabular">{tzOnly.length}</span>
            <span className="geo-stat__label">tz only</span>
          </div>
        </div>

        {pending > 0 && (
          <div className="geo-pending">
            <Loader2 size={13} className="geo-spin" />
            <span className="mono">Geocoding… {pending} location{pending > 1 ? "s" : ""} pending</span>
          </div>
        )}

        <div className="geo-legend">
          <span className="geo-legend__item">
            <span className="geo-legend__dot" style={{ background: SOURCE_COLOR.tweet_geo }} />
            <span className="mono">post location</span>
          </span>
          <span className="geo-legend__item">
            <span className="geo-legend__dot" style={{ background: SOURCE_COLOR.profile }} />
            <span className="mono">profile</span>
          </span>
        </div>

        <div className="geo-search searchbar">
          <span className="searchbar__icon">
            <Search size={14} />
          </span>
          <input
            className="searchbar__input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter pinned accounts…"
            autoComplete="off"
            spellCheck={false}
          />
        </div>

        {/* Located list */}
        <div className="geo-list">
          {filteredPoints.map((p) => (
            <button
              key={p.username}
              type="button"
              className="geo-list__row"
              onClick={() => flyTo(p)}
            >
              <span
                className="geo-list__dot"
                style={{ background: SOURCE_COLOR[p.source] ?? "#7d8187" }}
              />
              <span className="geo-list__main">
                <span className="mono geo-list__handle">@{p.username}</span>
                <span className="geo-list__loc text-mute">{p.location_text}</span>
              </span>
              <MapPin size={12} className="geo-list__icon" />
            </button>
          ))}
          {filteredPoints.length === 0 && !isLoading && (
            <p className="body-sm text-mute geo-list__empty">
              {points.length === 0
                ? "No accounts geocoded yet. Crawl some accounts that have a location set."
                : "No matches."}
            </p>
          )}
        </div>

        {/* Timezone-only list */}
        {tzOnly.length > 0 && (
          <div className="geo-tzsection">
            <span className="eyebrow eyebrow--sm">
              <Clock size={11} /> Located by timezone only
            </span>
            <div className="geo-tzlist">
              {tzOnly.slice(0, 40).map((t) => (
                <div key={t.username} className="geo-tzrow">
                  <span className="mono geo-tzrow__handle">@{t.username}</span>
                  <span className="mono text-mute">
                    UTC{t.timezone_utc_offset >= 0 ? "+" : ""}
                    {t.timezone_utc_offset} · ~{Math.round(t.approx_longitude)}°
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {isError && (
          <p className="body-sm geo-error">
            {(error as Error)?.message ?? "Failed to load map data."}{" "}
            <button type="button" className="geo-retry" onClick={() => refetch()}>
              Retry
            </button>
          </p>
        )}
      </aside>

      {/* Map */}
      <div className="geo-map-wrap">
        {isLoading && (
          <div className="geo-map-overlay">
            <Loader2 size={28} className="geo-spin" />
            <span className="body-sm text-mute" style={{ marginTop: 10 }}>
              Loading map…
            </span>
          </div>
        )}
        <div ref={containerRef} className="geo-map" />
      </div>
    </div>
  );
}
