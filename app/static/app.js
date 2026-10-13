"use strict";

const form = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const uploadButton = document.getElementById("upload-btn");
const messageEl = document.getElementById("message");
const resultsEl = document.getElementById("results");
const summaryEl = document.getElementById("summary");
const tableBody = document.querySelector("#features-table tbody");

// Maps expect longitude/latitude, so we ask the API for EPSG:4326 geometries.
const DISPLAY_CRS = "EPSG:4326";

const COLORS = { area: "#1f6feb", length: "#e8710a", point: "#1a7f37", other: "#8a8f98" };

let map = null;
let featureGroup = null;

const formatNumber = (n) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });

function setMessage(text, kind = "") {
  messageEl.textContent = text;
  messageEl.className = kind;
}

function setBusy(busy) {
  uploadButton.disabled = busy;
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
    // response had no JSON body
  }
  if (!response.ok) throw new Error(errorText(body, response.status));
  return body;
}

function featureName(feature) {
  const props = feature.properties || {};
  return props.Name || props.name || `Feature ${feature.feature_index}`;
}

function formatMeasurement(measurement) {
  if (!measurement) return null;
  if (measurement.type === "area") {
    const hectares = measurement.value / 10000;
    return `${formatNumber(measurement.value)} m² (${formatNumber(hectares)} ha)`;
  }
  return `${formatNumber(measurement.value)} m`;
}

function colorFor(feature) {
  if (feature.measurement) return COLORS[feature.measurement.type];
  if (feature.geometry_type === "Point" || feature.geometry_type === "MultiPoint") return COLORS.point;
  return COLORS.other;
}

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

function renderSummary(data) {
  summaryEl.replaceChildren();
  const items = [
    ["File", data.filename],
    ["Features", String(data.feature_count)],
    ["File CRS", data.crs ?? "\u2014"],
    ["Measured in", data.projected_crs ?? "\u2014"],
  ];
  for (const [label, value] of items) {
    const group = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = value;
    group.append(dt, dd);
    summaryEl.append(group);
  }
}

function renderMap(features) {
  if (featureGroup) map.removeLayer(featureGroup);
  featureGroup = L.featureGroup().addTo(map);

  const layersByIndex = new Map();
  for (const feature of features) {
    if (!feature.geometry) continue;
    const color = colorFor(feature);
    const layer = L.geoJSON(feature.geometry, {
      style: () => ({ color, weight: 3, fillOpacity: 0.25 }),
      pointToLayer: (_geometry, latlng) => L.circleMarker(latlng, { radius: 7, color, fillOpacity: 0.8 }),
    });
    layer.bindPopup(() => popupContent(feature));
    featureGroup.addLayer(layer);
    layersByIndex.set(feature.feature_index, layer);
  }

  const bounds = featureGroup.getBounds();
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 17 });
  return layersByIndex;
}

function renderTable(features, layersByIndex) {
  tableBody.replaceChildren();
  for (const feature of features) {
    const row = document.createElement("tr");

    for (const text of [String(feature.feature_index), featureName(feature), feature.geometry_type ?? "\u2014"]) {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.append(cell);
    }

    const measurementCell = document.createElement("td");
    measurementCell.textContent = formatMeasurement(feature.measurement) ?? "\u2014";
    if (feature.note) {
      const note = document.createElement("span");
      note.className = "note";
      note.textContent = feature.note;
      measurementCell.append(note);
    }
    row.append(measurementCell);

    const layer = layersByIndex.get(feature.feature_index);
    if (layer) {
      const zoomToFeature = () => {
        const bounds = layer.getBounds();
        if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 17 });
      };
      row.tabIndex = 0;
      row.addEventListener("click", zoomToFeature);
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter") zoomToFeature();
      });
    }

    tableBody.append(row);
  }
}

function render(data) {
  resultsEl.hidden = false;
  ensureMap();
  map.invalidateSize(); // the map was hidden, so tell Leaflet its real size
  renderSummary(data);
  const layersByIndex = renderMap(data.features);
  renderTable(data.features, layersByIndex);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  setBusy(true);
  setMessage("Uploading and processing\u2026");
  try {
    const body = new FormData();
    body.append("file", file);
    const info = await apiRequest("/api/files/", { method: "POST", body });
    const data = await apiRequest(`/api/files/${info.id}/measurements/?crs=${DISPLAY_CRS}`);
    render(data);
    setMessage(`Done: ${data.feature_count} feature(s) processed.`, "ok");
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    setBusy(false);
  }
});