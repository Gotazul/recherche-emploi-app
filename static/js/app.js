// ── API helper ────────────────────────────────────────────────────────────────
const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async put(path, body) {
    const r = await fetch(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async del(path) {
    const r = await fetch(path, { method: "DELETE" });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
};

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type = "is-info") {
  const c = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ── Statuts ───────────────────────────────────────────────────────────────────
const STATUS_LABEL = {
  new: "Nouvelle", viewed: "Vue", interesting: "Intéressante",
  applied: "Candidatée", dismissed: "Écartée", gone: "Disparue"
};

function statusTag(s) {
  return `<span class="tag status-${s}">${STATUS_LABEL[s] || s}</span>`;
}

// ── Router ────────────────────────────────────────────────────────────────────
const VIEWS = { dashboard: renderDashboard, listings: renderListings, profiles: renderProfiles, sites: renderSites, search: renderSearch, compare: renderCompare };
let currentView = "dashboard";

function navigate(view) {
  currentView = view;
  document.querySelectorAll(".nav-item").forEach(el => {
    el.classList.toggle("is-active", el.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach(el => {
    el.classList.toggle("is-active", el.id === `view-${view}`);
  });
  (VIEWS[view] || (() => {}))();
}

document.querySelectorAll(".nav-item[data-view]").forEach(el => {
  el.addEventListener("click", e => { e.preventDefault(); navigate(el.dataset.view); });
});

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function renderDashboard() {
  const [stats, profiles] = await Promise.all([api.get("/api/dashboard"), api.get("/api/profiles")]);

  document.getElementById("dash-total").textContent = stats.total;
  document.getElementById("dash-new").textContent = stats.by_status?.new || 0;
  document.getElementById("dash-interesting").textContent = stats.by_status?.interesting || 0;
  document.getElementById("dash-applied").textContent = stats.by_status?.applied || 0;

  document.getElementById("dash-by-site").innerHTML = Object.entries(stats.by_site || {}).map(([name, count]) =>
    `<tr><td>${name}</td><td class="has-text-right"><strong>${count}</strong></td></tr>`
  ).join("") || `<tr><td colspan="2" class="has-text-grey">Aucune offre</td></tr>`;

  document.getElementById("dash-recent").innerHTML = stats.recent_new.length
    ? stats.recent_new.map(l => offreMiniCard(l)).join("")
    : `<p class="has-text-grey">Aucune nouvelle offre</p>`;

  document.getElementById("dash-profiles").innerHTML = profiles.length
    ? profiles.filter(p => p.active).map(p =>
        `<div class="mb-2">
          <button class="button is-link is-light" onclick="launchSearchAndNavigate('${p.id}')">
            <span class="icon"><i class="fas fa-search"></i></span>
            <span>Rechercher — ${p.name}</span>
          </button>
        </div>`
      ).join("")
    : `<p class="has-text-grey">Aucun profil créé. <a onclick="navigate('profiles')">Créer un profil</a></p>`;
}

function offreMiniCard(l) {
  return `<div class="box p-3 mb-2" style="cursor:pointer" onclick="openListingDetail('${l.id}')">
    <div class="is-flex is-align-items-center gap-2">
      <div style="flex:1;min-width:0">
        <p class="has-text-weight-semibold is-size-7 mb-0" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${l.title || "—"}</p>
        <p class="is-size-7 has-text-grey mb-0">${l.site_name} · ${l.company || "—"} · ${l.contract_type || "—"}</p>
      </div>
      <div class="ml-3 has-text-right" style="white-space:nowrap">
        <p class="is-size-7 has-text-grey mb-0">${l.location || "—"}</p>
        ${statusTag(l.status)}
      </div>
    </div>
  </div>`;
}

// ── Offres ────────────────────────────────────────────────────────────────────
let compareSet = new Set();
let listingsFilters = {};

async function renderListings() {
  const [profiles, sites] = await Promise.all([api.get("/api/profiles"), api.get("/api/sites")]);

  document.getElementById("filter-profile").innerHTML = `<option value="">Tous les profils</option>` +
    profiles.map(p => `<option value="${p.id}">${p.name}</option>`).join("");

  document.getElementById("filter-site").innerHTML = `<option value="">Tous les sites</option>` +
    sites.map(s => `<option value="${s.id}">${s.name}</option>`).join("");

  await loadListings();
}

async function loadListings() {
  const params = new URLSearchParams();
  if (listingsFilters.profile_id)   params.set("profile_id", listingsFilters.profile_id);
  if (listingsFilters.site_id)      params.set("site_id", listingsFilters.site_id);
  if (listingsFilters.status)       params.set("status", listingsFilters.status);
  if (listingsFilters.contract_type) params.set("contract_type", listingsFilters.contract_type);
  if (listingsFilters.remote)       params.set("remote", listingsFilters.remote);

  const data = await api.get(`/api/listings?${params}`);
  document.getElementById("listings-total").textContent = data.total;
  renderListingsTable(data.items);
}

function renderListingsTable(items) {
  const tbody = document.getElementById("listings-tbody");
  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="has-text-centered has-text-grey py-5">Aucune offre trouvée</td></tr>`;
    return;
  }
  tbody.innerHTML = items.map(l => `
    <tr>
      <td><input type="checkbox" class="compare-cb" data-id="${l.id}" ${compareSet.has(l.id) ? "checked" : ""}></td>
      <td>
        <a onclick="openListingDetail('${l.id}')" style="cursor:pointer">${l.title || "—"}</a>
        <br><span class="is-size-7 has-text-grey">${l.site_name}</span>
      </td>
      <td>${l.company || "—"}</td>
      <td>${l.contract_type ? `<span class="tag is-light">${l.contract_type}</span>` : "—"}</td>
      <td>${l.location || "—"}</td>
      <td>${l.remote || "—"}</td>
      <td class="has-text-weight-semibold">${l.salary || "—"}</td>
      <td>${statusTag(l.status)}</td>
      <td>
        <div class="buttons are-small">
          <button class="button is-light" title="Détail" onclick="openListingDetail('${l.id}')"><span class="icon"><i class="fas fa-eye"></i></span></button>
          <a class="button is-light" href="${l.url}" target="_blank" title="Voir l'offre"><span class="icon"><i class="fas fa-external-link-alt"></i></span></a>
          <button class="button is-danger is-light" title="Supprimer" onclick="deleteListing('${l.id}')"><span class="icon"><i class="fas fa-trash"></i></span></button>
        </div>
      </td>
    </tr>
  `).join("");

  tbody.querySelectorAll(".compare-cb").forEach(cb => {
    cb.addEventListener("change", () => {
      if (cb.checked) compareSet.add(cb.dataset.id);
      else compareSet.delete(cb.dataset.id);
      document.getElementById("compare-count").textContent = compareSet.size;
    });
  });

  applyTextFilter();
}

function applyTextFilter() {
  const q = (document.getElementById("filter-text")?.value || "").toLowerCase().trim();
  document.querySelectorAll("#listings-tbody tr").forEach(tr => {
    if (!q) { tr.style.display = ""; return; }
    const text = tr.textContent.toLowerCase();
    tr.style.display = text.includes(q) ? "" : "none";
  });
}

function applyListingsFilters() {
  listingsFilters = {
    profile_id:    document.getElementById("filter-profile").value,
    site_id:       document.getElementById("filter-site").value,
    status:        document.getElementById("filter-status").value,
    contract_type: document.getElementById("filter-contract").value,
    remote:        document.getElementById("filter-remote").value,
  };
  loadListings();
}

async function deleteListing(id) {
  if (!confirm("Supprimer cette offre ?")) return;
  await api.del(`/api/listings/${id}`);
  compareSet.delete(id);
  toast("Offre supprimée", "is-success");
  loadListings();
}

// ── Détail modal ──────────────────────────────────────────────────────────────
async function openListingDetail(id) {
  const l = await api.get(`/api/listings/${id}`);
  const modal = document.getElementById("modal-listing");

  modal.querySelector(".modal-card-title").textContent = l.title || "Offre";

  modal.querySelector("#detail-info").innerHTML = `
    <table class="table is-narrow is-fullwidth">
      <tbody>
        <tr><td>Entreprise</td><td><strong>${l.company || "—"}</strong></td></tr>
        <tr><td>Contrat</td><td>${l.contract_type || "—"}</td></tr>
        <tr><td>Localisation</td><td>${l.location || "—"}</td></tr>
        <tr><td>Télétravail</td><td>${l.remote || "—"}</td></tr>
        <tr><td>Salaire</td><td>${l.salary || "—"}</td></tr>
        <tr><td>Site</td><td>${l.site_name}</td></tr>
        <tr><td>Profil</td><td>${l.profile_name}</td></tr>
        <tr><td>Détectée le</td><td>${l.first_detected?.slice(0,10) || "—"}</td></tr>
        <tr><td>Dernière détection</td><td>${l.last_detected?.slice(0,10) || "—"}</td></tr>
      </tbody>
    </table>
    ${l.description ? `<p class="is-size-7 has-text-grey mb-3" style="white-space:pre-wrap">${l.description.slice(0, 400)}${l.description.length > 400 ? "…" : ""}</p>` : ""}
    <a href="${l.url}" target="_blank" class="button is-link is-light is-small">
      <span class="icon"><i class="fas fa-external-link-alt"></i></span><span>Voir l'offre originale</span>
    </a>
  `;

  const statusSel = modal.querySelector("#detail-status");
  statusSel.value = l.status;
  statusSel.onchange = async () => {
    await api.put(`/api/listings/${id}`, { status: statusSel.value });
    toast("Statut mis à jour", "is-success");
    if (currentView === "listings") loadListings();
    if (currentView === "dashboard") renderDashboard();
  };

  const notesEl = modal.querySelector("#detail-notes");
  notesEl.value = l.notes || "";
  modal.querySelector("#detail-save-notes").onclick = async () => {
    await api.put(`/api/listings/${id}`, { notes: notesEl.value });
    toast("Notes enregistrées", "is-success");
  };

  modal.classList.add("is-active");

  // Marquer comme vue si nouvelle
  if (l.status === "new") {
    await api.put(`/api/listings/${id}`, { status: "viewed" });
    statusSel.value = "viewed";
    if (currentView === "listings") loadListings();
    if (currentView === "dashboard") renderDashboard();
  }
}

document.getElementById("modal-listing").querySelector(".modal-close")?.addEventListener("click", () => {
  document.getElementById("modal-listing").classList.remove("is-active");
});
document.getElementById("modal-listing").querySelector(".modal-background")?.addEventListener("click", () => {
  document.getElementById("modal-listing").classList.remove("is-active");
});

// ── Comparateur ───────────────────────────────────────────────────────────────
async function renderCompare() {
  const container = document.getElementById("compare-grid");
  if (!compareSet.size) {
    container.innerHTML = `<p class="has-text-grey">Aucune offre sélectionnée. Sélectionne des offres dans la vue <a onclick="navigate('listings')">Offres</a>.</p>`;
    return;
  }
  const items = await api.get(`/api/listings/compare?ids=${[...compareSet].join(",")}`);
  container.innerHTML = items.map(l => `
    <div class="card compare-card">
      <div class="card-content p-3">
        <p class="has-text-weight-semibold is-size-6 mb-1">${l.title || "—"}</p>
        <table class="table is-narrow is-fullwidth is-borderless mb-2">
          <tr><td class="has-text-grey is-size-7">Entreprise</td><td><strong>${l.company || "—"}</strong></td></tr>
          <tr><td class="has-text-grey is-size-7">Contrat</td><td>${l.contract_type || "—"}</td></tr>
          <tr><td class="has-text-grey is-size-7">Lieu</td><td>${l.location || "—"}</td></tr>
          <tr><td class="has-text-grey is-size-7">Télétravail</td><td>${l.remote || "—"}</td></tr>
          <tr><td class="has-text-grey is-size-7">Salaire</td><td>${l.salary || "—"}</td></tr>
          <tr><td class="has-text-grey is-size-7">Site</td><td>${l.site_name}</td></tr>
          <tr><td class="has-text-grey is-size-7">Statut</td><td>${statusTag(l.status)}</td></tr>
        </table>
        <div class="buttons are-small">
          <a href="${l.url}" target="_blank" class="button is-link is-light is-small">Voir l'offre</a>
          <button class="button is-light is-small" onclick="openListingDetail('${l.id}')">Détail</button>
          <button class="button is-danger is-light is-small" onclick="compareSet.delete('${l.id}');renderCompare()">Retirer</button>
        </div>
      </div>
    </div>
  `).join("");
}

// ── Recherche ─────────────────────────────────────────────────────────────────
let _searchSites = [];

async function renderSearch() {
  const profiles = await api.get("/api/profiles");
  const sel = document.getElementById("search-profile-sel");
  sel.innerHTML = `<option value="">— Choisir un profil —</option>` +
    profiles.filter(p => p.active).map(p => `<option value="${p.id}">${p.name}</option>`).join("");

  const lastProfile = localStorage.getItem("lastSearchProfile");
  if (lastProfile && sel.querySelector(`option[value="${lastProfile}"]`)) {
    sel.value = lastProfile;
    const sites = await api.get("/api/sites");
    _searchSites = sites.filter(s => s.active);
    _renderSitePending();
  }

  sel.onchange = async () => {
    if (!sel.value) { document.getElementById("search-results").innerHTML = ""; return; }
    localStorage.setItem("lastSearchProfile", sel.value);
    const sites = await api.get("/api/sites");
    _searchSites = sites.filter(s => s.active);
    _renderSitePending();
  };
}

function _renderSitePending() {
  document.getElementById("search-results").innerHTML =
    _searchSites.map(s => _siteRowHtml(s.id, s.name, null)).join("");
}

function _siteRowHtml(siteId, siteName, state) {
  const loading = state === "loading";
  const done    = state && state !== "loading";
  const hasErr  = done && state.error && !state.listings_found;
  const hasNew  = done && state.new > 0;

  const badge = loading
    ? `<span class="tag is-info is-light"><span class="icon is-small"><i class="fas fa-spinner fa-spin"></i></span>&nbsp;Recherche…</span>`
    : done
      ? hasErr
        ? `<span class="tag is-warning">Erreur</span>`
        : `<span class="tag is-light">${state.listings_found} offre(s)${hasNew ? ` · <b>${state.new} nouv.</b>` : ""}</span>`
      : `<span class="tag is-light has-text-grey">En attente</span>`;

  const detail = done ? `
    <p class="is-size-7 mt-1">
      ${state.listings_found} offre(s) correspondante(s)${state.filtered_out > 0 ? ` <span class="has-text-grey">(${state.filtered_out} filtrées)</span>` : ""}
      ${hasNew ? `· <span class="has-text-success">${state.new} nouvelle(s)</span>` : ""}
      · <a href="${state.search_url}" target="_blank">Ouvrir <i class="fas fa-external-link-alt"></i></a>
    </p>
    ${state.error ? `<p class="is-size-7 has-text-warning-dark">${state.error}</p>` : ""}
  ` : `<p class="is-size-7 has-text-grey mt-1">—</p>`;

  return `
    <div class="search-result-site${hasNew ? " has-results" : ""}${hasErr ? " has-error" : ""}" id="site-row-${siteId}">
      <div class="is-flex is-align-items-center is-justify-content-space-between">
        <strong>${siteName}</strong>
        <div class="is-flex is-align-items-center" style="gap:0.5rem">
          ${badge}
          <button class="button is-small is-light" title="Relancer ce site"
            onclick="launchSingleSearch('${siteId}')" ${loading ? "disabled" : ""}>
            <span class="icon is-small"><i class="fas fa-redo-alt"></i></span>
          </button>
        </div>
      </div>
      ${detail}
    </div>`;
}

function _updateSiteRow(siteResult) {
  const row = document.getElementById(`site-row-${siteResult.site_id}`);
  if (!row) return;
  const name = row.querySelector("strong").textContent;
  row.outerHTML = _siteRowHtml(siteResult.site_id, name, siteResult);
}

function _setSiteLoading(siteId) {
  const row = document.getElementById(`site-row-${siteId}`);
  if (!row) return;
  const name = row.querySelector("strong").textContent;
  row.outerHTML = _siteRowHtml(siteId, name, "loading");
}

async function launchSearch(profileId) {
  if (!profileId) { toast("Sélectionne un profil", "is-danger"); return; }
  _searchSites.forEach(s => _setSiteLoading(s.id));
  try {
    const result = await api.post(`/api/search/${profileId}`);
    result.sites.forEach(s => _updateSiteRow(s));
    _showSearchSummary(result);
  } catch(e) {
    toast("Erreur lors de la recherche : " + e.message, "is-danger");
    _renderSitePending();
  }
}

async function launchSingleSearch(siteId) {
  const profileId = document.getElementById("search-profile-sel").value;
  if (!profileId) { toast("Sélectionne un profil", "is-danger"); return; }
  _setSiteLoading(siteId);
  try {
    const result = await api.post(`/api/search/${profileId}?site_ids=${siteId}`);
    if (result.sites[0]) _updateSiteRow(result.sites[0]);
    if (result.total_new > 0) toast(`${result.total_new} nouvelle(s) offre(s) trouvée(s) !`, "is-success");
  } catch(e) {
    toast("Erreur : " + e.message, "is-danger");
    const row = document.getElementById(`site-row-${siteId}`);
    if (row) { const n = row.querySelector("strong").textContent; row.outerHTML = _siteRowHtml(siteId, n, null); }
  }
}

function _showSearchSummary(result) {
  const el = document.getElementById("search-results");
  const html = `<div id="search-summary-notif" class="notification is-light mb-3">
    <strong>${result.profile_name}</strong> —
    <span class="has-text-success">${result.total_new} nouvelle(s)</span>,
    ${result.total_updated} mise(s) à jour
  </div>`;
  const notif = document.getElementById("search-summary-notif");
  if (notif) notif.outerHTML = html;
  else el.insertAdjacentHTML("afterbegin", html);
}

async function launchSearchAndNavigate(profileId) {
  localStorage.setItem("lastSearchProfile", profileId);
  navigate("search");
  const sel = document.getElementById("search-profile-sel");
  if (sel) sel.value = profileId;
  if (!_searchSites.length) {
    const sites = await api.get("/api/sites");
    _searchSites = sites.filter(s => s.active);
    _renderSitePending();
  }
  await launchSearch(profileId);
}

document.getElementById("btn-search-launch").addEventListener("click", async () => {
  const profileId = document.getElementById("search-profile-sel").value;
  if (!profileId) { toast("Sélectionne un profil", "is-danger"); return; }
  if (!_searchSites.length) {
    const sites = await api.get("/api/sites");
    _searchSites = sites.filter(s => s.active);
    _renderSitePending();
  }
  await launchSearch(profileId);
});

// ── Profils CRUD ──────────────────────────────────────────────────────────────
let editingProfileId = null;

async function renderProfiles() {
  const profiles = await api.get("/api/profiles");
  const el = document.getElementById("profiles-list");
  el.innerHTML = profiles.length
    ? profiles.map(p => `
        <div class="box mb-3">
          <div class="is-flex is-align-items-center is-justify-content-space-between">
            <div>
              <span class="has-text-weight-semibold">${p.name}</span>
              ${p.active ? "" : `<span class="tag is-light ml-2">Inactif</span>`}
              <br>
              <span class="is-size-7 has-text-grey">${criteriaPreview(p.criteria)}</span>
            </div>
            <div class="buttons are-small">
              <button class="button is-link is-light" onclick="editProfile('${p.id}')">Modifier</button>
              <button class="button is-danger is-light" onclick="deleteProfile('${p.id}')">Supprimer</button>
            </div>
          </div>
        </div>
      `).join("")
    : `<p class="has-text-grey">Aucun profil. Crée-en un ci-dessous.</p>`;
}

function criteriaPreview(c) {
  if (typeof c === "string") c = JSON.parse(c);
  const parts = [];
  if (c.keywords?.length) parts.push(c.keywords.join(", "));
  if (c.experience_levels?.length) parts.push(c.experience_levels.join(" / "));
  if (c.contract_types?.length) parts.push(c.contract_types.join(" / "));
  if (c.location) parts.push(c.location);
  if (c.radius_km) parts.push(`${c.radius_km} km`);
  if (c.remote && c.remote !== "indifferent") parts.push(c.remote === "full" ? "100% remote" : "télétravail partiel");
  return parts.join(" · ") || "Critères vides";
}

async function editProfile(id) {
  const p = await api.get(`/api/profiles/${id}`);
  editingProfileId = id;
  fillProfileForm(p);
  document.getElementById("profile-form-title").textContent = "Modifier le profil";
  document.getElementById("profile-form-section").style.display = "block";
  document.getElementById("profile-form-section").scrollIntoView({ behavior: "smooth" });
}

function fillProfileForm(p) {
  const c = typeof p.criteria === "string" ? JSON.parse(p.criteria) : (p.criteria || {});
  document.getElementById("pf-name").value = p.name || "";
  document.getElementById("pf-keywords").value = (c.keywords || []).join(", ");
  document.getElementById("pf-location").value = c.location || "";
  document.getElementById("pf-radius").value = c.radius_km || "";
  document.getElementById("pf-remote").value = c.remote || "indifferent";
  document.querySelectorAll(".pf-contract").forEach(cb => {
    cb.checked = (c.contract_types || []).includes(cb.value);
  });
  document.querySelectorAll(".pf-experience").forEach(cb => {
    cb.checked = (c.experience_levels || []).includes(cb.value);
  });
}

function getProfileFormData() {
  const splitTrim = v => v.split(",").map(s => s.trim()).filter(Boolean);
  const contracts   = [...document.querySelectorAll(".pf-contract:checked")].map(cb => cb.value);
  const experiences = [...document.querySelectorAll(".pf-experience:checked")].map(cb => cb.value);
  return {
    name: document.getElementById("pf-name").value.trim(),
    criteria: {
      keywords:         splitTrim(document.getElementById("pf-keywords").value),
      experience_levels: experiences,
      contract_types:   contracts,
      location:         document.getElementById("pf-location").value.trim(),
      radius_km:        parseInt(document.getElementById("pf-radius").value) || null,
      remote:           document.getElementById("pf-remote").value,
    }
  };
}

document.getElementById("btn-profile-new").addEventListener("click", () => {
  editingProfileId = null;
  fillProfileForm({ name: "", criteria: {} });
  document.getElementById("profile-form-title").textContent = "Nouveau profil";
  document.getElementById("profile-form-section").style.display = "block";
  document.getElementById("profile-form-section").scrollIntoView({ behavior: "smooth" });
});

document.getElementById("btn-profile-save").addEventListener("click", async () => {
  const data = getProfileFormData();
  if (!data.name) { toast("Le nom est requis", "is-danger"); return; }
  if (editingProfileId) {
    await api.put(`/api/profiles/${editingProfileId}`, data);
    toast("Profil mis à jour", "is-success");
  } else {
    await api.post("/api/profiles", data);
    toast("Profil créé", "is-success");
  }
  document.getElementById("profile-form-section").style.display = "none";
  editingProfileId = null;
  renderProfiles();
});

document.getElementById("btn-profile-cancel").addEventListener("click", () => {
  document.getElementById("profile-form-section").style.display = "none";
  editingProfileId = null;
});

async function deleteProfile(id) {
  if (!confirm("Supprimer ce profil ? Les offres associées resteront.")) return;
  await api.del(`/api/profiles/${id}`);
  toast("Profil supprimé", "is-success");
  renderProfiles();
}

// ── Sites CRUD ────────────────────────────────────────────────────────────────
let editingSiteId = null;

async function renderSites() {
  const sites = await api.get("/api/sites");
  document.getElementById("sites-list").innerHTML = sites.map(s => `
    <div class="box mb-3">
      <div class="is-flex is-align-items-center is-justify-content-space-between">
        <div>
          <span class="has-text-weight-semibold">${s.name}</span>
          <span class="tag mode-${s.access_mode} ml-2">${s.access_mode}</span>
          ${s.active ? `<span class="tag is-success is-light ml-1">Actif</span>` : `<span class="tag is-light ml-1">Inactif</span>`}
          <br><span class="is-size-7 has-text-grey">${s.url_base}</span>
        </div>
        <div class="buttons are-small">
          <button class="button is-light" onclick="toggleSite('${s.id}', ${s.active})">${s.active ? "Désactiver" : "Activer"}</button>
          <button class="button is-link is-light" onclick="editSite('${s.id}')">Modifier</button>
          <button class="button is-danger is-light" onclick="deleteSite('${s.id}')">Supprimer</button>
        </div>
      </div>
    </div>
  `).join("");
}

async function toggleSite(id, currentActive) {
  await api.put(`/api/sites/${id}`, { active: !currentActive });
  renderSites();
}

function _toggleCredentialsSection(name) {
  const show = name.toLowerCase().includes("france travail");
  document.getElementById("sf-credentials-section").style.display = show ? "block" : "none";
}

async function editSite(id) {
  const s = await api.get(`/api/sites/${id}`);
  editingSiteId = id;
  document.getElementById("sf-name").value = s.name;
  document.getElementById("sf-url").value = s.url_base;
  document.getElementById("sf-mode").value = s.access_mode;
  document.getElementById("site-form-title").textContent = "Modifier le site";
  _toggleCredentialsSection(s.name);
  // Pré-remplit le Client ID si déjà configuré
  document.getElementById("sf-client-id").value = "";
  document.getElementById("sf-client-secret").value = "";
  if (s.name.toLowerCase().includes("france travail")) {
    const creds = await api.get(`/api/sites/${id}/credentials`).catch(() => null);
    if (creds?.client_id) document.getElementById("sf-client-id").value = creds.client_id;
  }
  document.getElementById("site-form-section").style.display = "block";
  document.getElementById("site-form-section").scrollIntoView({ behavior: "smooth" });
}

document.getElementById("sf-name").addEventListener("input", e => _toggleCredentialsSection(e.target.value));

document.getElementById("btn-site-new").addEventListener("click", () => {
  editingSiteId = null;
  document.getElementById("sf-name").value = "";
  document.getElementById("sf-url").value = "https://";
  document.getElementById("sf-mode").value = "direct";
  document.getElementById("sf-client-id").value = "";
  document.getElementById("sf-client-secret").value = "";
  document.getElementById("sf-credentials-section").style.display = "none";
  document.getElementById("site-form-title").textContent = "Nouveau site";
  document.getElementById("site-form-section").style.display = "block";
});

document.getElementById("btn-site-save").addEventListener("click", async () => {
  const data = {
    name: document.getElementById("sf-name").value.trim(),
    url_base: document.getElementById("sf-url").value.trim(),
    access_mode: document.getElementById("sf-mode").value,
  };
  if (!data.name || !data.url_base) { toast("Nom et URL requis", "is-danger"); return; }
  let siteId = editingSiteId;
  if (siteId) {
    await api.put(`/api/sites/${siteId}`, data);
  } else {
    const created = await api.post("/api/sites", data);
    siteId = created.id;
  }
  // Sauvegarde les credentials France Travail si renseignés
  const clientId     = document.getElementById("sf-client-id").value.trim();
  const clientSecret = document.getElementById("sf-client-secret").value.trim();
  if (data.name.toLowerCase().includes("france travail") && (clientId || clientSecret)) {
    await api.post(`/api/sites/${siteId}/credentials`, { client_id: clientId, client_secret: clientSecret });
  }
  toast(editingSiteId ? "Site mis à jour" : "Site ajouté", "is-success");
  document.getElementById("site-form-section").style.display = "none";
  editingSiteId = null;
  renderSites();
});

document.getElementById("btn-site-cancel").addEventListener("click", () => {
  document.getElementById("site-form-section").style.display = "none";
  editingSiteId = null;
});

async function deleteSite(id) {
  if (!confirm("Supprimer ce site ?")) return;
  await api.del(`/api/sites/${id}`);
  toast("Site supprimé", "is-success");
  renderSites();
}

// ── Filtres listeners ─────────────────────────────────────────────────────────
document.getElementById("filter-text")?.addEventListener("input", applyTextFilter);

["filter-profile","filter-site","filter-status","filter-contract","filter-remote"].forEach(id => {
  document.getElementById(id)?.addEventListener("change", applyListingsFilters);
});

document.getElementById("btn-compare")?.addEventListener("click", () => {
  if (compareSet.size < 2) { toast("Sélectionne au moins 2 offres", "is-danger"); return; }
  navigate("compare");
});

document.getElementById("btn-clear-listings")?.addEventListener("click", async () => {
  const pid = document.getElementById("filter-profile").value;
  const scope = pid ? "ce profil" : "TOUS les profils";
  if (!confirm(`Supprimer toutes les offres de ${scope} ?`)) return;
  const url = pid ? `/api/listings?profile_id=${pid}` : "/api/listings";
  const data = await (await fetch(url, { method: "DELETE" })).json();
  toast(`${data.deleted} offre(s) supprimée(s)`, "is-success");
  compareSet.clear();
  document.getElementById("compare-count").textContent = "0";
  loadListings();
  renderDashboard();
});

document.getElementById("btn-export")?.addEventListener("click", () => {
  const pid = document.getElementById("filter-profile").value;
  if (!pid) { toast("Sélectionne un profil pour l'export", "is-danger"); return; }
  window.open(`/api/export/${pid}`, "_blank");
});

function debounce(fn, delay) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}

// ── Init ──────────────────────────────────────────────────────────────────────
navigate("dashboard");
