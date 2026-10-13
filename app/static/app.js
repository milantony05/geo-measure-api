"use strict";

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const messageEl = document.getElementById("message");
const resultsEl = document.getElementById("results");
const statsEl = document.getElementById("stats");
const exportButton = document.getElementById("export-btn");
const tableBody = document.querySelector("#features-table tbody");

const DISPLAY_CRS = "EPSG:4326"; // web maps expect longitude/latitude
const ALLOWED_EXTENSIONS = [".kml", ".zip"];
const COLORS = { area: "#3b82f6", length: "#f97316", point: "#22c55e", other: "#9ca3af" };
const KIND_NAMES = { area: "polygon", length: "line", point: "point", other: "other" };

let map = null;
let featureGroup = null;
let entries = new Map(); // feature_index -> { row, layer, kind }
let selected = null;

/* ---------- Formatting helpers ---------- */

const formatNumber = (n) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });

function formatArea(squareMetres) {
  if (squareMetres >= 1e6) return `${formatNumber(squareMetres / 1e6)} km\u00B2`;
  if (squareMetres >= 1e4) return `${formatNumber(squareMetres / 1e4)} ha`;
  return `${formatNumber(squareMetres)} m\u00B2`;
}

function formatLength(metres) {
  return metres >= 1000 ? `${formatNumber(metres / 1000)} km` : `${formatNumber(metres)} m`;
}

function formatMeasurement(measurement) {
  if (!measurement) return null;
  return measurement.type === "area"
    ? `${formatNumber(measurement.value)} m\u00B2`
    : `${formatNumber(measurement.value)} m`;
}

function featureName(feature) {
  const props = feature.properties || {};
  return props.Name || props.name || `Feature ${feature.feature_index}`;
}

function kindOf(feature) {
  if (feature.measurement) return feature.measurement.type; // "area" or "length"
  if (feature.geometry_type === "Point" || feature.geometry_type === "MultiPoint") return "point";
  return "other";
}

const baseStyle = (kind) => ({ color: COLORS[kind], weight: kind === "point" ? 2 : 3, fillOpacity: kind === "point" ? 0.85 : 0.25 });
const selectedStyle = (kind) => ({ color: COLORS[kind], weight: 6, fillOpacity: kind === "point" ? 1 : 0.45 });

/* ---------- Messages and API calls ---------- */

function setMessage(text, kind = "") {
  messageEl.textContent = text;
  messageEl.className = kind;
}

function setBusy(busy) {
  dropzone.classList.toggle("busy", busy);
  fileInput.disabled = busy;
}

// The API reports errors as {detail: "text"} or {detail: {message: "text", ...}}.
function errorText(body, status) {
  const detail = body && body.detail;
  if (typeof detail === "string") return detail;
  if (detail && detail.message) return detail.message;
  return `Request failed (HTTP ${status}).`;
}

async function apiRequest(path, options) {
  const response = await fetch(path, options);
  let body = null;
  try {
    body = await response.json();
  } catch (_) {
    // the response had no JSON body
  }
  if (!response.ok) throw new Error(errorText(body, response.status));
  return body;
}

/* ---------- Rendering ---------- */

function ensureMap() {
  if (map) return;
  map = L.map("map").setView([20, 0], 2);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
}

// Popups are built from DOM nodes with textContent, never innerHTML:
// names and properties come from the uploaded file, which we must not trust.
function popupContent(feature) {
  const box = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = featureName(feature);
  box.append(title, document.createElement("br"));
  box.append(`${feature.geometry_type} \u2014 ${formatMeasurement(feature.measurement) ?? "no measurement"}`);
  return box;
}

function statCard(label, value, sub) {
  const card = document.createElement("div");
  card.className = "stat";
  const labelEl = document.createElement("div");
  labelEl.className = "stat-label";
  labelEl.textContent = label;
  const valueEl = document.createElement("div");
  valueEl.className = "stat-value";
  valueEl.textContent = value;
  const subEl = document.createElement("div");
  subEl.className = "stat-sub";
  subEl.textContent = sub;
  card.append(labelEl, valueEl, subEl);
  return card;
}

function renderStats(data) {
  const features = data.features;
  const total = (type) =>
    features.reduce((sum, f) => (f.measurement && f.measurement.type === type ? sum + f.measurement.value : sum), 0);
  const count = (kind) => features.filter((f) => kindOf(f) === kind).length;

  const breakdown = ["area", "length", "point", "other"]
    .map((kind) => [count(kind), KIND_NAMES[kind]])
    .filter(([n]) => n > 0)
    .map(([n, name]) => `${n} ${name}${n === 1 ? "" : "s"}`)
    .join(" \u00B7 ");

  const totalArea = total("area");
  const totalLength = total("length");

  statsEl.replaceChildren(
    statCard("Features", String(data.feature_count), breakdown || "\u2014"),
    statCard("Total area", count("area") ? formatArea(totalArea) : "\u2014", count("area") ? `${formatNumber(totalArea)} m\u00B2` : "No polygons"),
    statCard("Total length", count("length") ? formatLength(totalLength) : "\u2014", count("length") ? `${formatNumber(totalLength)} m` : "No lines"),
    statCard("Measured in", data.projected_crs ?? "\u2014", `File CRS: ${data.crs ?? "unknown"}`),
  );
}

function select(index, { zoom }) {
  const entry = entries.get(index);
  if (!entry) return;

  if (selected && selected !== entry) {
    selected.row.classList.remove("selected");
    selected.layer.setStyle(baseStyle(selected.kind));
  }
  selected = entry;
  entry.row.classList.add("selected");
  entry.layer.setStyle(selectedStyle(entry.kind));
  entry.row.scrollIntoView({ block: "nearest" });

  if (zoom) {
    const bounds = entry.layer.getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 17 });
  }
}

function renderFeatures(features) {
  if (featureGroup) map.removeLayer(featureGroup);
  featureGroup = L.featureGroup().addTo(map);
  entries = new Map();
  selected = null;
  tableBody.replaceChildren();

  for (const feature of features) {
    const kind = kindOf(feature);

    // --- table row ---
    const row = document.createElement("tr");

    const indexCell = document.createElement("td");
    indexCell.textContent = String(feature.feature_index);

    const nameCell = document.createElement("td");
    nameCell.textContent = featureName(feature);
    const layerName = feature.properties && feature.properties.source_layer;
    if (layerName) {
      const sub = document.createElement("span");
      sub.className = "sub";
      sub.textContent = layerName;
      nameCell.append(sub);
    }

    const typeCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.dataset.kind = kind;
    badge.textContent = feature.geometry_type ?? "No geometry";
    typeCell.append(badge);

    const measurementCell = document.createElement("td");
    measurementCell.className = "num";
    measurementCell.textContent = formatMeasurement(feature.measurement) ?? "\u2014";
    if (feature.note) {
      const note = document.createElement("span");
      note.className = "note";
      note.textContent = feature.note;
      measurementCell.append(note);
    }

    row.append(indexCell, nameCell, typeCell, measurementCell);
    tableBody.append(row);

    // --- map layer (only for features that have geometry) ---
    if (!feature.geometry) continue;

    const layer = L.geoJSON(feature.geometry, {
      style: () => baseStyle(kind),
      pointToLayer: (_geometry, latlng) => L.circleMarker(latlng, { radius: 7 }),
    });
    layer.bindPopup(() => popupContent(feature));
    layer.on("click", () => select(feature.feature_index, { zoom: false }));
    featureGroup.addLayer(layer);

    entries.set(feature.feature_index, { row, layer, kind });
    row.tabIndex = 0;
    row.addEventListener("click", () => select(feature.feature_index, { zoom: true }));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select(feature.feature_index, { zoom: true });
      }
    });
  }

  const bounds = featureGroup.getBounds();
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 17 });
}

function render(data) {
  resultsEl.hidden = false;
  ensureMap();
  map.invalidateSize(); // the map container was hidden, so tell Leaflet its real size
  renderStats(data);
  renderFeatures(data.features);
  exportButton.href = `/api/files/${data.id}/measurements.csv`;
}

/* ---------- Uploading ---------- */

async function handleFile(file) {
  if (!file) return;

  const lowerName = file.name.toLowerCase();
  if (!ALLOWED_EXTENSIONS.some((ext) => lowerName.endsWith(ext))) {
    setMessage("Please choose a .kml file, or a .zip containing a Shapefile.", "error");
    return;
  }

  setBusy(true);
  setMessage("");
  try {
    const body = new FormData();
    body.append("file", file);
    const info = await apiRequest("/api/files/", { method: "POST", body });
    const data = await apiRequest(`/api/files/${info.id}/measurements/?crs=${DISPLAY_CRS}`);
    render(data);
    setMessage(`${data.filename}: ${data.feature_count} feature${data.feature_count === 1 ? "" : "s"} processed.`, "ok");
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    setBusy(false);
    fileInput.value = ""; // lets the same file be chosen again
  }
}

fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  handleFile(event.dataTransfer.files[0]);
});

// A file dropped outside the drop area would make the browser navigate away to it.
for (const type of ["dragover", "drop"]) {
  window.addEventListener(type, (event) => event.preventDefault());
}