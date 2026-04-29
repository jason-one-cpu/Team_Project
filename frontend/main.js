const uiState = {
  authMode: "register",
  role: "customer",
  currentUser: null,
  sessionToken: localStorage.getItem("cityhopSessionToken") || "",
  currentPage: "products",
  currentManagerSection: "store-manager",
  selectedManagerStoreId: null,
  expandedManagerUserId: "",
  selectedScooterId: "",
  data: {
    users: [],
    scooters: [],
    bookings: [],
    issues: [],
    priceMap: {},
    statistics: {
      weeklyIncomeByOption: [],
      dailyIncome: []
    },
    summary: {
      availableScooters: 0,
      activeBookings: 0,
      totalBookings: 0,
      totalRevenue: 0,
      openIssues: 0,
      highPriorityIssues: 0,
      fleetAvailability: 0
    }
  }
};

const authScreen = document.getElementById("auth-screen");
const appShell = document.getElementById("app-shell");
const authTitle = document.getElementById("auth-title");
const authSubtitle = document.getElementById("auth-subtitle");
const authRoleLabel = document.getElementById("auth-role-label");
const authFeedback = document.getElementById("auth-feedback");
const registerForm = document.getElementById("register-form");
const loginForm = document.getElementById("login-form");
const authModeButtons = document.querySelectorAll("[data-auth-mode]");
const roleButtons = document.querySelectorAll("[data-role]");
const tabs = document.querySelectorAll(".tab[data-page]");
const managerNavTabs = document.querySelectorAll(".manager-nav-tab");
const pages = document.querySelectorAll(".page");
const customerTabs = document.querySelectorAll(".customer-tab");
const managerSections = document.querySelectorAll(".manager-section");
const bookingForm = document.getElementById("booking-form");
const issueForm = document.getElementById("issue-form");
const storeForm = document.getElementById("store-form");
const managerScooterForm = document.getElementById("manager-scooter-form");
const logoutButton = document.getElementById("logout-button");
const backToProductsButton = document.getElementById("back-to-products-button");
let scooterMap = null;
let scooterMarkers = [];
let userLocationMarker = null;
let routeMap = null;
let routePolyline = null;
let routeMarkers = [];
let managerStoreMap = null;
let managerStoreMarkers = [];
let pendingStoreMarker = null;
let expandedRouteBookingId = null;
let hasRequestedUserLocation = false;
let selectedStore = "City Square";
const cityCentreView = { lat: 52.9530, lng: -1.1500, zoom: 17 };
const defaultUserLocation = { lat: 52.9518, lng: -1.1538, label: "Default customer location" };
let lastStoreCheckKey = "";
let currentMapCenter = { lat: defaultUserLocation.lat, lng: defaultUserLocation.lng, zoom: 17 };
let currentUserCoords = { lat: defaultUserLocation.lat, lng: defaultUserLocation.lng };
let hasInitializedNearestStore = false;
let selectedStoreWasManual = false;

function populateStoreForm(store) {
  const modeLabel = document.getElementById("store-form-mode");
  const submitButton = document.getElementById("store-submit-button");
  const cancelButton = document.getElementById("store-cancel-edit-button");
  const deleteButton = document.getElementById("store-delete-button");
  document.getElementById("store-name").value = store.name;
  document.getElementById("store-latitude").value = Number(store.latitude).toFixed(6);
  document.getElementById("store-longitude").value = Number(store.longitude).toFixed(6);
  uiState.selectedManagerStoreId = store.id;
  if (modeLabel) {
    modeLabel.textContent = `Editing ${store.name}. Update the name or location, then save.`;
  }
  if (submitButton) {
    submitButton.textContent = "Save store";
  }
  if (cancelButton) {
    cancelButton.classList.remove("hidden");
  }
  if (deleteButton) {
    deleteButton.classList.remove("hidden");
  }
}

function resetStoreForm() {
  const modeLabel = document.getElementById("store-form-mode");
  const submitButton = document.getElementById("store-submit-button");
  const cancelButton = document.getElementById("store-cancel-edit-button");
  const deleteButton = document.getElementById("store-delete-button");
  uiState.selectedManagerStoreId = null;
  storeForm?.reset();
  if (pendingStoreMarker) {
    pendingStoreMarker.remove();
    pendingStoreMarker = null;
  }
  if (modeLabel) {
    modeLabel.textContent = "Create a new store by clicking a location on the map.";
  }
  if (submitButton) {
    submitButton.textContent = "Create store";
  }
  if (cancelButton) {
    cancelButton.classList.add("hidden");
  }
  if (deleteButton) {
    deleteButton.classList.add("hidden");
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(uiState.sessionToken ? { "X-Session-Token": uiState.sessionToken } : {}),
      ...(options.headers || {})
    },
    ...options
  });
  const contentType = response.headers.get("Content-Type") || "";
  const raw = await response.text();
  let data = {};

  if (contentType.includes("application/json")) {
    data = raw ? JSON.parse(raw) : {};
  } else {
    throw new Error("Backend API is not running. Please start the app with `python backend/server.py` and open http://127.0.0.1:8000.");
  }

  if (!response.ok) {
    throw new Error(data.error || "Request failed.");
  }
  return data;
}

async function loadState() {
  const data = await api("/api/state");
  uiState.data = data;
  return data;
}

async function hashClientPassword(password) {
  const encoder = new TextEncoder();
  const bytes = encoder.encode(password);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

function getCurrentUserRecord() {
  if (!uiState.currentUser) {
    return null;
  }
  return uiState.data.users.find((user) => user.id === uiState.currentUser.id) || null;
}

function setAuthMode(mode) {
  const normalizedMode = uiState.role === "manager" ? "login" : mode;
  uiState.authMode = normalizedMode;
  authModeButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.authMode === normalizedMode);
    button.classList.toggle("hidden", uiState.role === "manager" && button.dataset.authMode === "register");
  });
  registerForm.classList.toggle("hidden", normalizedMode !== "register");
  loginForm.classList.toggle("hidden", normalizedMode !== "login");
  authTitle.textContent = normalizedMode === "register" ? "Create account" : "Sign in";
  authSubtitle.textContent = normalizedMode === "register"
    ? `Register a new ${uiState.role} account to enter the platform.`
    : `Login as a ${uiState.role} to continue into the platform.`;
  authFeedback.textContent = uiState.role === "manager"
    ? "Manager access is login-only. Use the default admin / admin account."
    : "Accounts are now handled through the SQLite-backed backend.";
}

function setRole(role) {
  uiState.role = role;
  roleButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.role === role);
  });
  authRoleLabel.textContent = role === "manager" ? "Manager Access" : "Customer Access";
  document.getElementById("login-button").textContent = "Login";
  setAuthMode(role === "manager" ? "login" : uiState.authMode);
}

function setPage(pageId) {
  uiState.currentPage = pageId;
  tabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.page === pageId);
  });
  pages.forEach((page) => {
    page.classList.toggle("is-active", page.id === `${pageId}-page`);
  });

  if (pageId === "products" && scooterMap) {
    window.setTimeout(() => {
      scooterMap.invalidateSize();
      scooterMap.setView([currentMapCenter.lat, currentMapCenter.lng], currentMapCenter.zoom || 17);
      requestUserLocation();
    }, 80);
  }
}

function setManagerSection(sectionId) {
  uiState.currentManagerSection = sectionId;
  managerNavTabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.managerSection === sectionId);
  });
  managerSections.forEach((section) => {
    section.classList.toggle("is-active", section.id === `${sectionId}-section`);
  });

  if (sectionId === "store-manager" && managerStoreMap) {
    window.setTimeout(() => managerStoreMap.invalidateSize(), 80);
  }
}

function setBookingSelection(scooterId) {
  uiState.selectedScooterId = scooterId;
  renderBookingFormDetails();
  renderBookingEstimate();
}

function enterApp(user) {
  uiState.currentUser = user;
  authScreen.classList.add("hidden");
  appShell.classList.remove("hidden");
  document.getElementById("welcome-text").textContent = `Welcome, ${user.name}`;
  document.getElementById("welcome-role").textContent = user.role === "manager" ? "Manager" : "Customer";
  document.getElementById("app-title").textContent = user.role === "manager" ? "Manager Portal" : "Customer Portal";
  customerTabs.forEach((tab) => tab.classList.toggle("hidden", user.role === "manager"));
  managerNavTabs.forEach((tab) => tab.classList.toggle("hidden", user.role !== "manager"));
  if (user.role === "manager") {
    setPage("manager");
    setManagerSection(uiState.currentManagerSection || "store-manager");
  } else {
    setPage("products");
  }
  renderAll();
}

async function logout() {
  try {
    await api("/api/logout", { method: "POST", body: JSON.stringify({}) });
  } catch (error) {
    // Ignore logout failures and still clear local state.
  }

  uiState.currentUser = null;
  uiState.sessionToken = "";
  localStorage.removeItem("cityhopSessionToken");
  appShell.classList.add("hidden");
  authScreen.classList.remove("hidden");
  setAuthMode("login");
}

function renderScooterSelects() {
  const issueSelect = document.getElementById("issue-scooter");
  const guestStoreSelect = document.getElementById("guest-store-select");
  const guestScooterSelect = document.getElementById("guest-scooter-select");
  const previousGuestStoreId = guestStoreSelect?.value;
  const previousGuestScooterId = guestScooterSelect?.value;

  issueSelect.innerHTML = uiState.data.scooters
    .map((scooter) => `<option value="${scooter.id}">${scooter.id} - ${scooter.location}</option>`)
    .join("");

  if (guestStoreSelect) {
    guestStoreSelect.innerHTML = uiState.data.stores
      .map((store) => `<option value="${store.id}">${store.name}</option>`)
      .join("");
    if (previousGuestStoreId && Array.from(guestStoreSelect.options).some((option) => option.value === previousGuestStoreId)) {
      guestStoreSelect.value = previousGuestStoreId;
    }
  }

  if (guestScooterSelect) {
    const selectedStoreId = Number(guestStoreSelect?.value || uiState.data.stores[0]?.id || 0);
    const availableScooters = uiState.data.scooters.filter(
      (scooter) => scooter.available && scooter.storeId === selectedStoreId
    );
    guestScooterSelect.innerHTML = availableScooters
      .map(
        (scooter) =>
          `<option value="${scooter.id}">${scooter.id} - ${scooter.location} - GBP ${scooter.hourlyPrice}/hour</option>`
      )
      .join("");
    if (previousGuestScooterId && Array.from(guestScooterSelect.options).some((option) => option.value === previousGuestScooterId)) {
      guestScooterSelect.value = previousGuestScooterId;
    }
  }
}

function syncGuestBookingDefaults() {
  const startInput = document.getElementById("guest-start-time");
  const endInput = document.getElementById("guest-end-time");
  if (!startInput || !endInput) {
    return;
  }
  if (!startInput.value) {
    const start = new Date();
    start.setMinutes(0, 0, 0);
    start.setHours(start.getHours() + 1);
    startInput.value = formatDateTimeLocalValue(start);
  }
  if (!endInput.value) {
    const end = new Date(startInput.value);
    end.setHours(end.getHours() + 1);
    endInput.value = formatDateTimeLocalValue(end);
  }
}

function getSelectedScooter() {
  return uiState.data.scooters.find((scooter) => scooter.id === uiState.selectedScooterId) || null;
}

function formatDateTimeLocalValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function calculateBookingEstimate() {
  const scooter = getSelectedScooter();
  const startInput = document.getElementById("booking-start-time");
  const endInput = document.getElementById("booking-end-time");

  if (!scooter || !startInput || !endInput || !startInput.value || !endInput.value) {
    return null;
  }

  const start = new Date(startInput.value);
  const end = new Date(endInput.value);
  const milliseconds = end - start;
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || milliseconds <= 0) {
    return { valid: false };
  }

  const durationHours = Math.max(1, Math.ceil(milliseconds / 3600000));
  const discount = calculateExpectedDiscount(durationHours);
  const baseCost = durationHours * scooter.hourlyPrice;
  return {
    valid: true,
    durationHours,
    estimatedCost: Math.max(1, Math.round(baseCost * (1 - discount.rate))),
    baseCost,
    discount
  };
}

function calculateExpectedDiscount(durationHours) {
  const user = getCurrentUserRecord();
  if (!user || !uiState.currentUser) {
    return { label: "None", rate: 0 };
  }

  const currentWeekHours = uiState.data.bookings
    .filter((booking) => booking.customer === uiState.currentUser.name)
    .reduce((total, booking) => total + (Number(booking.durationHours) || 0), 0);

  const discounts = [{ label: "None", rate: 0 }];
  if (currentWeekHours + durationHours >= 8) {
    discounts.push({ label: "Frequent user", rate: 0.12 });
  }
  if (user.accountType === "student") {
    discounts.push({ label: "Student", rate: 0.10 });
  }
  if (user.accountType === "senior") {
    discounts.push({ label: "Senior", rate: 0.15 });
  }

  return discounts.sort((left, right) => right.rate - left.rate)[0];
}

function syncBookingTimeDefaults() {
  const startInput = document.getElementById("booking-start-time");
  const endInput = document.getElementById("booking-end-time");
  if (!startInput || !endInput) {
    return;
  }

  if (!startInput.value) {
    const start = new Date();
    start.setMinutes(0, 0, 0);
    start.setHours(start.getHours() + 1);
    startInput.value = formatDateTimeLocalValue(start);
  }

  if (!endInput.value) {
    const end = new Date(startInput.value);
    end.setHours(end.getHours() + 1);
    endInput.value = formatDateTimeLocalValue(end);
  }

  renderBookingEstimate();
}

function renderBookingFormDetails() {
  const details = document.getElementById("booking-scooter-details");
  const scooter = getSelectedScooter();
  const savedCardRow = document.getElementById("saved-card-row");
  const savedCardCheckbox = document.getElementById("use-saved-card");
  const savedCardLabel = document.getElementById("saved-card-label");
  if (!details) {
    return;
  }

  if (!scooter) {
    details.innerHTML = `
      <div>
        <span></span>
        <strong></strong>
      </div>
    `;
    return;
  }

  details.innerHTML = `
    <div><span>${scooter.id}</span><strong>${scooter.location} - GBP ${scooter.hourlyPrice}/hour</strong></div>
    <div><span>Pickup store</span><strong>${scooter.location}</strong></div>
    <div><span>Battery</span><strong>${scooter.battery}%</strong></div>
    <div><span>Hourly price</span><strong>GBP ${scooter.hourlyPrice}/hour</strong></div>
  `;

  const currentUserRecord = getCurrentUserRecord();
  if (savedCardRow && savedCardCheckbox && savedCardLabel) {
    const hasSavedCard = Boolean(currentUserRecord?.hasSavedCard);
    savedCardRow.classList.toggle("hidden", !hasSavedCard);
    savedCardCheckbox.checked = false;
    savedCardLabel.textContent = hasSavedCard
      ? `Use saved card: ${currentUserRecord.savedCardLabel}`
      : "Use saved card";
  }

  syncBookingTimeDefaults();
  updatePaymentFieldVisibility();
}

function renderBookingEstimate() {
  const estimate = document.getElementById("booking-estimate");
  if (!estimate) {
    return;
  }

  const scooter = getSelectedScooter();
  if (!scooter) {
    estimate.innerHTML = `
      <div><span>Estimated duration</span><strong>Select a scooter first</strong></div>
      <div><span>Estimated cost</span><strong>-</strong></div>
    `;
    return;
  }

  const result = calculateBookingEstimate();
  if (!result) {
    estimate.innerHTML = `
      <div><span>Estimated duration</span><strong>Choose start and end times</strong></div>
      <div><span>Estimated cost</span><strong>-</strong></div>
    `;
    return;
  }

  if (!result.valid) {
    estimate.innerHTML = `
      <div><span>Estimated duration</span><strong>End time must be later than start time</strong></div>
      <div><span>Estimated cost</span><strong>-</strong></div>
    `;
    return;
  }

  estimate.innerHTML = `
    <div><span>Estimated duration</span><strong>${result.durationHours} hour(s)</strong></div>
    <div><span>Base cost</span><strong>GBP ${result.baseCost}</strong></div>
    <div><span>Discount</span><strong>${result.discount.label} (${Math.round(result.discount.rate * 100)}%)</strong></div>
    <div><span>Estimated cost</span><strong>GBP ${result.estimatedCost}</strong></div>
  `;
}

function updatePaymentFieldVisibility() {
  const useSavedCard = document.getElementById("use-saved-card")?.checked;
  const newCardFields = document.getElementById("new-card-fields");
  const saveCardOption = document.getElementById("save-card-for-future")?.closest(".checkbox-row");
  if (newCardFields) {
    newCardFields.classList.toggle("hidden", Boolean(useSavedCard));
  }
  if (saveCardOption) {
    saveCardOption.classList.toggle("hidden", Boolean(useSavedCard));
  }
}

function getStoreSummaries() {
  const grouped = new Map();
  uiState.data.scooters.forEach((scooter) => {
    if (!grouped.has(scooter.location)) {
      grouped.set(scooter.location, []);
    }
    grouped.get(scooter.location).push(scooter);
  });

  return Array.from(grouped.entries()).map(([storeName, scootersAtStore]) => {
    const availableScooters = scootersAtStore.filter((scooter) => scooter.available);
    const point = scootersAtStore[0]
      ? { lat: scootersAtStore[0].latitude, lng: scootersAtStore[0].longitude }
      : { lat: cityCentreView.lat, lng: cityCentreView.lng };
    return {
      storeName,
      point,
      scootersAtStore,
      availableScooters
    };
  });
}

function setSelectedStore(storeName) {
  selectedStore = storeName;
  selectedStoreWasManual = true;
  renderStoreLegend();
}

function distanceBetweenPoints(lat1, lng1, lat2, lng2) {
  const earthRadiusKm = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLng / 2) * Math.sin(dLng / 2);
  return 2 * earthRadiusKm * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function selectNearestStore(lat, lng, force = false) {
  const stores = getStoreSummaries();
  if (!stores.length) {
    return;
  }
  if (selectedStoreWasManual && !force) {
    return;
  }

  const nearest = stores.reduce((closest, store) => {
    const distance = distanceBetweenPoints(lat, lng, store.point.lat, store.point.lng);
    if (!closest || distance < closest.distance) {
      return { storeName: store.storeName, distance };
    }
    return closest;
  }, null);

  if (nearest) {
    selectedStore = nearest.storeName;
    if (!selectedStoreWasManual) {
      hasInitializedNearestStore = true;
    }
  }
}

function renderScooterMap() {
  const map = document.getElementById("scooter-map");
  if (!map) {
    return;
  }

  if (!window.L) {
    map.innerHTML = `
      <div class="map-fallback">
        <strong>Map unavailable</strong>
        <span>Leaflet or the online map tiles could not be loaded.</span>
      </div>
    `;
    return;
  }

  if (!scooterMap) {
    scooterMap = window.L.map(map, {
      zoomControl: true,
      attributionControl: true
    }).setView([cityCentreView.lat, cityCentreView.lng], cityCentreView.zoom);

    window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(scooterMap);
  }

  scooterMarkers.forEach((marker) => marker.remove());
  scooterMarkers = [];

  getStoreSummaries().forEach((store) => {
    const point = store.point || { lat: 52.9530, lng: -1.1500 };
    const markerHtml = `
      <div class="map-pin ${store.availableScooters.length > 0 ? "map-pin--available" : "map-pin--booked"}">
        <span>${store.storeName}</span>
      </div>
    `;

    const marker = window.L.marker([point.lat, point.lng], {
      icon: window.L.divIcon({
        className: "map-pin-wrapper",
        html: markerHtml,
        iconSize: [22, 22],
        iconAnchor: [11, 11],
        popupAnchor: [0, -10]
      })
    });

    marker.bindPopup(`
      <strong>${store.storeName}</strong><br>
      ${store.availableScooters.length} scooter(s) available<br>
      ${store.scootersAtStore.length} scooter(s) in total
    `);

    marker.on("click", () => {
      setSelectedStore(store.storeName);
    });

    marker.addTo(scooterMap);
    scooterMarkers.push(marker);
  });

  window.setTimeout(() => {
    scooterMap.invalidateSize();
  }, 80);

  if (!hasInitializedNearestStore && currentUserCoords) {
    selectNearestStore(currentUserCoords.lat, currentUserCoords.lng, true);
  }

  renderStoreLegend();
}

function renderStoreLegend() {
  const legend = document.getElementById("map-legend");
  if (!legend) {
    return;
  }

  const stores = getStoreSummaries();
  if (!stores.length) {
    legend.innerHTML = `
      <div class="map-legend__empty">
        <strong>No stores available</strong>
        <small>The fleet has not been assigned to pickup stores yet.</small>
      </div>
    `;
    return;
  }

  const activeStore = stores.find((store) => store.storeName === selectedStore) || stores[0];
  selectedStore = activeStore.storeName;

  const availableList = activeStore.availableScooters.length
    ? activeStore.availableScooters
        .map(
          (scooter) => `
            <div class="map-legend__item">
              <span class="map-legend__dot map-legend__dot--available"></span>
              <div>
                <strong>${scooter.id}</strong>
                <small>Battery ${scooter.battery}% - GBP ${scooter.hourlyPrice}/hour</small>
              </div>
              <button type="button" class="button button--primary store-book-button" data-scooter-id="${scooter.id}">Book</button>
            </div>
          `
        )
        .join("")
    : `
      <div class="map-legend__empty">
        <strong>No scooters available</strong>
        <small>All scooters at ${activeStore.storeName} are currently booked.</small>
      </div>
    `;

  legend.innerHTML = `
    <div class="map-legend__header">
      <p class="card__eyebrow">Selected Store</p>
      <h3>${activeStore.storeName}</h3>
      <p class="muted">${activeStore.availableScooters.length} available out of ${activeStore.scootersAtStore.length} scooter(s).</p>
    </div>
    <div class="map-legend__list">
      ${availableList}
    </div>
  `;

  document.querySelectorAll(".store-book-button").forEach((button) => {
    button.addEventListener("click", () => {
      setBookingSelection(button.dataset.scooterId);
      setPage("book");
    });
  });
}

function showUserLocation(lat, lng, message = "Your current location has been added to the map.") {
  if (!window.L || !scooterMap) {
    return;
  }

  currentUserCoords = { lat, lng };
  if (userLocationMarker) {
    userLocationMarker.remove();
  }

  userLocationMarker = window.L.circleMarker([lat, lng], {
    radius: 10,
    color: "#ffffff",
    weight: 3,
    fillColor: "#1d4ed8",
    fillOpacity: 1
  });

  userLocationMarker.bindPopup("<strong>You are here</strong>");
  userLocationMarker.bindTooltip("You are here", {
    permanent: true,
    direction: "top",
    offset: [0, -12],
    className: "user-location-tooltip"
  });
  userLocationMarker.addTo(scooterMap);
  currentMapCenter = { lat, lng, zoom: 17 };
  scooterMap.setView([lat, lng], 17);
  if (!selectedStoreWasManual) {
    selectNearestStore(lat, lng, true);
  }
  renderStoreLegend();
  document.getElementById("map-feedback").textContent = message;
}

function showDefaultUserLocation(message = "Using the default customer location until live geolocation is available.") {
  showUserLocation(defaultUserLocation.lat, defaultUserLocation.lng, message);
}

async function ensureNearbyStores(lat, lng) {
  const locationKey = `${lat.toFixed(3)},${lng.toFixed(3)}`;
  if (lastStoreCheckKey === locationKey) {
    return;
  }
  lastStoreCheckKey = locationKey;

  try {
    const result = await api("/api/stores/ensure-nearby", {
      method: "POST",
      body: JSON.stringify({ latitude: lat, longitude: lng })
    });
    uiState.data = result.state;
    renderAll();
  } catch (error) {
    document.getElementById("map-feedback").textContent = error.message;
  }
}

function requestUserLocation() {
  if (hasRequestedUserLocation) {
    return;
  }
  hasRequestedUserLocation = true;

  if (!navigator.geolocation) {
    showDefaultUserLocation("Geolocation is not supported by this browser, so the default customer location is shown.");
    ensureNearbyStores(defaultUserLocation.lat, defaultUserLocation.lng);
    return;
  }

  showDefaultUserLocation("Requesting your live location. The default customer location is shown for now.");
  ensureNearbyStores(defaultUserLocation.lat, defaultUserLocation.lng);
  navigator.geolocation.getCurrentPosition(
    async (position) => {
      showUserLocation(position.coords.latitude, position.coords.longitude);
      await ensureNearbyStores(position.coords.latitude, position.coords.longitude);
    },
    async (error) => {
      if (error.code === error.PERMISSION_DENIED) {
        showDefaultUserLocation("Location permission was denied, so the default customer location is shown.");
        await ensureNearbyStores(defaultUserLocation.lat, defaultUserLocation.lng);
        return;
      }
      if (error.code === error.POSITION_UNAVAILABLE) {
        showDefaultUserLocation("Your live location is unavailable, so the default customer location is shown.");
        await ensureNearbyStores(defaultUserLocation.lat, defaultUserLocation.lng);
        return;
      }
      if (error.code === error.TIMEOUT) {
        showDefaultUserLocation("The location request timed out, so the default customer location is shown.");
        await ensureNearbyStores(defaultUserLocation.lat, defaultUserLocation.lng);
        return;
      }
      showDefaultUserLocation("Could not retrieve your live location, so the default customer location is shown.");
      await ensureNearbyStores(defaultUserLocation.lat, defaultUserLocation.lng);
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0
    }
  );
}

function renderBookingSummary() {
  const summary = document.getElementById("booking-summary");
  if (!summary) {
    return;
  }
  const booking = [...uiState.data.bookings].reverse().find((item) => item.status === "Active") || uiState.data.bookings[uiState.data.bookings.length - 1];

  if (!booking) {
    summary.innerHTML = "<div><span>No booking yet</span><strong>Create your first hire</strong></div>";
    return;
  }

  summary.innerHTML = `
    <div><span>Customer</span><strong>${booking.customer}</strong></div>
    <div><span>Scooter</span><strong>${booking.scooterId}</strong></div>
    <div><span>Start time</span><strong>${booking.startTime || "Not recorded"}</strong></div>
    <div><span>End time</span><strong>${booking.endTime || "Not recorded"}</strong></div>
    <div><span>Duration</span><strong>${booking.durationHours} hours</strong></div>
    <div><span>Cost</span><strong>GBP ${booking.price}</strong></div>
    <div><span>Status</span><strong>${booking.status}</strong></div>
  `;
}

function renderPriceConfiguration() {
}

function renderManagerStoreOptions() {
  const select = document.getElementById("manager-store-select");
  if (!select) {
    return;
  }

  select.innerHTML = uiState.data.stores
    .map((store) => `<option value="${store.id}">${store.name} (${store.availableCount}/${store.scooterCount} available)</option>`)
    .join("");
  if (uiState.data.stores.length) {
    if (!select.value) {
      select.value = String(uiState.data.stores[0].id);
    }
    const selectedStoreId = Number(select.value);
    if (!uiState.data.stores.some((store) => store.id === selectedStoreId)) {
      select.value = String(uiState.data.stores[0].id);
    }
  }
}

function renderManagerStoreInventory() {
  const container = document.getElementById("manager-store-scooters");
  if (!container) {
    return;
  }

  const selectedStoreId = Number(document.getElementById("manager-store-select")?.value || 0);
  const store = uiState.data.stores.find((item) => item.id === selectedStoreId) || uiState.data.stores[0];
  if (!store) {
    container.innerHTML = "<div><span>No stores yet</span><strong>Create the first store on the map.</strong></div>";
    return;
  }

  const scooters = uiState.data.scooters.filter((scooter) => scooter.storeId === store.id);
  container.innerHTML = scooters
    .map(
      (scooter) => `
        <div>
          <span>${scooter.id} / ${scooter.battery}% battery / ${scooter.available ? "Available" : "Booked"}</span>
          <div class="fleet__actions">
            <input type="number" min="1" value="${scooter.hourlyPrice}" class="manager-price-input" data-scooter-id="${scooter.id}">
            <button type="button" class="button button--ghost manager-save-price-button" data-scooter-id="${scooter.id}">Save price</button>
            <button type="button" class="button button--danger manager-delete-scooter-button" data-scooter-id="${scooter.id}">Delete</button>
          </div>
        </div>
      `
    )
    .join("") || "<div><span>No scooters in this store</span><strong>Add one below.</strong></div>";

  document.querySelectorAll(".manager-save-price-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const input = document.querySelector(`.manager-price-input[data-scooter-id="${button.dataset.scooterId}"]`);
      try {
        const result = await api("/api/scooters/hourly-prices", {
          method: "POST",
          body: JSON.stringify({ scooterPrices: { [button.dataset.scooterId]: Number(input.value) } })
        });
        uiState.data = result.state;
        document.getElementById("manager-scooter-feedback").textContent = result.message;
        renderAll();
      } catch (error) {
        document.getElementById("manager-scooter-feedback").textContent = error.message;
      }
    });
  });

  document.querySelectorAll(".manager-delete-scooter-button").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const result = await api("/api/scooters/delete", {
          method: "POST",
          body: JSON.stringify({ scooterId: button.dataset.scooterId })
        });
        uiState.data = result.state;
        document.getElementById("manager-scooter-feedback").textContent = result.message;
        renderAll();
      } catch (error) {
        document.getElementById("manager-scooter-feedback").textContent = error.message;
      }
    });
  });
}

function renderManagerStoreMap() {
  const mapElement = document.getElementById("manager-store-map");
  if (!mapElement || !window.L || uiState.currentUser?.role !== "manager") {
    return;
  }

  if (!managerStoreMap) {
    managerStoreMap = window.L.map(mapElement, {
      zoomControl: true,
      attributionControl: true
    }).setView([cityCentreView.lat, cityCentreView.lng], 14);

    window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(managerStoreMap);

    managerStoreMap.on("click", (event) => {
      const { lat, lng } = event.latlng;
      uiState.selectedManagerStoreId = null;
      document.getElementById("store-latitude").value = lat.toFixed(6);
      document.getElementById("store-longitude").value = lng.toFixed(6);
      document.getElementById("store-name").focus();
      document.getElementById("store-form-mode").textContent = "Creating a new store at the selected location.";
      document.getElementById("store-submit-button").textContent = "Create store";
      document.getElementById("store-cancel-edit-button").classList.add("hidden");
      document.getElementById("store-delete-button").classList.add("hidden");

      if (pendingStoreMarker) {
        pendingStoreMarker.remove();
      }
      pendingStoreMarker = window.L.marker([lat, lng]).addTo(managerStoreMap);
      document.getElementById("store-feedback").textContent = "Store location selected on the map.";
    });
  }

  managerStoreMarkers.forEach((marker) => marker.remove());
  managerStoreMarkers = [];

  uiState.data.stores.forEach((store) => {
    const marker = window.L.marker([store.latitude, store.longitude]).addTo(managerStoreMap);
    marker.bindPopup(`
      <strong>${store.name}</strong><br>
      ${store.availableCount} available / ${store.scooterCount} total
    `);
    marker.on("click", () => {
      populateStoreForm(store);
      const storeSelect = document.getElementById("manager-store-select");
      if (storeSelect) {
        storeSelect.value = String(store.id);
      }
      renderManagerStoreInventory();
      document.getElementById("store-feedback").textContent = `Loaded ${store.name}. You can now edit and save it.`;
    });
    managerStoreMarkers.push(marker);
  });

  window.setTimeout(() => managerStoreMap.invalidateSize(), 80);
}

function renderBookingHistory() {
  const customerBookings = uiState.currentUser
    ? uiState.data.bookings.filter((booking) => booking.customer === uiState.currentUser.name)
    : [];

  const customerContent = customerBookings
    .slice()
    .reverse()
    .map(
      (booking) => `
          <div class="booking-entry ${expandedRouteBookingId === booking.id ? "booking-entry--expanded" : ""}">
            <div class="booking-entry__summary">
              <span>${booking.customer} / ${booking.scooterId}</span>
              <strong>${booking.startTime || "-"} to ${booking.endTime || "-"} / GBP ${booking.price} / ${booking.status}</strong>
              <div class="fleet__actions">
                <button type="button" class="button button--ghost view-route-button" data-booking-id="${booking.id}">${expandedRouteBookingId === booking.id ? "Hide route" : "View route"}</button>
                ${booking.status === "Active" ? `
                  <select class="booking-extend-select" data-booking-id="${booking.id}">
                    <option value="1">+1 hour</option>
                    <option value="4">+4 hours</option>
                    <option value="24">+1 day</option>
                  </select>
                  <button type="button" class="button button--ghost extend-booking-button" data-booking-id="${booking.id}">Extend</button>
                ` : ""}
                ${booking.status === "Active" ? `<button type="button" class="button button--ghost history-end-button" data-booking-id="${booking.id}">End</button>` : ""}
              </div>
            </div>
            <div class="booking-entry__meta">
              <span>Payment: ${booking.paymentMethod} / ${booking.paymentStatus}</span>
              <span>Discount: ${booking.discountType}</span>
              <span>Email: ${booking.confirmationEmailStatus}${booking.confirmationReference ? ` (${booking.confirmationReference})` : ""}</span>
            </div>
            ${expandedRouteBookingId === booking.id ? `
              <div class="booking-entry__route">
                <div class="map-stage map-stage--route" id="booking-route-map-${booking.id}"></div>
                <p class="feedback" id="route-feedback-${booking.id}">Loading route...</p>
              </div>
            ` : ""}
          </div>
        `
    )
    .join("");

  const managerContent = uiState.data.bookings
    .slice()
    .reverse()
    .map(
      (booking) => `
          <div>
            <span>${booking.customer} / ${booking.scooterId}</span>
            <strong>${booking.startTime || "-"} to ${booking.endTime || "-"} / GBP ${booking.price} / ${booking.status}</strong>
            <div class="fleet__actions">
              ${booking.status === "Active" ? `<button type="button" class="button button--ghost manager-end-booking-button" data-booking-id="${booking.id}">End</button><button type="button" class="button button--ghost manager-cancel-booking-button" data-booking-id="${booking.id}">Cancel</button>` : ""}
            </div>
          </div>
        `
    )
    .join("");

  document.getElementById("customer-booking-history").innerHTML =
    customerContent || "<div><span>No bookings yet</span><strong>Your bookings will appear here.</strong></div>";
  const managerHistory = document.getElementById("booking-history");
  if (managerHistory) {
    managerHistory.innerHTML = managerContent;
  }

  document.querySelectorAll(".history-end-button").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const result = await api("/api/bookings/end", {
          method: "POST",
          body: JSON.stringify({ bookingId: Number(button.dataset.bookingId) })
        });
        uiState.data = result.state;
        document.getElementById("booking-action-feedback").textContent = result.message;
        renderAll();
      } catch (error) {
        document.getElementById("booking-action-feedback").textContent = error.message;
      }
    });
  });

  document.querySelectorAll(".extend-booking-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const select = document.querySelector(`.booking-extend-select[data-booking-id="${button.dataset.bookingId}"]`);
      try {
        const result = await api("/api/bookings/extend", {
          method: "POST",
          body: JSON.stringify({
            bookingId: Number(button.dataset.bookingId),
            additionalHours: Number(select?.value || 1)
          })
        });
        uiState.data = result.state;
        document.getElementById("booking-action-feedback").textContent = result.message;
        renderAll();
      } catch (error) {
        document.getElementById("booking-action-feedback").textContent = error.message;
      }
    });
  });

  document.querySelectorAll(".manager-end-booking-button").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const result = await api("/api/bookings/end", {
          method: "POST",
          body: JSON.stringify({ bookingId: Number(button.dataset.bookingId) })
        });
        uiState.data = result.state;
        document.getElementById("booking-action-feedback").textContent = result.message;
        renderAll();
      } catch (error) {
        document.getElementById("booking-action-feedback").textContent = error.message;
      }
    });
  });

  document.querySelectorAll(".manager-cancel-booking-button").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const result = await api("/api/bookings/cancel", {
          method: "POST",
          body: JSON.stringify({ bookingId: Number(button.dataset.bookingId) })
        });
        uiState.data = result.state;
        document.getElementById("booking-action-feedback").textContent = result.message;
        renderAll();
      } catch (error) {
        document.getElementById("booking-action-feedback").textContent = error.message;
      }
    });
  });

  document.querySelectorAll(".view-route-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const bookingId = Number(button.dataset.bookingId);
      if (expandedRouteBookingId === bookingId) {
        expandedRouteBookingId = null;
        destroyRouteMap();
        renderBookingHistory();
        return;
      }

      expandedRouteBookingId = bookingId;
      destroyRouteMap();
      renderBookingHistory();
    });
  });

  if (expandedRouteBookingId && customerBookings.some((booking) => booking.id === expandedRouteBookingId)) {
    window.setTimeout(() => {
      showBookingRoute(expandedRouteBookingId);
    }, 50);
  }
}

async function showBookingRoute(bookingId) {
  const feedback = document.getElementById(`route-feedback-${bookingId}`);
  const mapElement = document.getElementById(`booking-route-map-${bookingId}`);

  if (!feedback || !mapElement) {
    return;
  }

  feedback.textContent = "Loading route...";

  try {
    const result = await api(`/api/bookings/route?bookingId=${bookingId}`);
    const { booking, route } = result;
    feedback.textContent = route.length
      ? `${route.length} GPS point(s) generated for this booking.`
      : "No GPS points are available for this booking yet.";

    if (!window.L) {
      feedback.textContent = "Leaflet could not be loaded for the route map.";
      return;
    }

    destroyRouteMap();

    routeMap = window.L.map(mapElement, {
      zoomControl: true,
      attributionControl: true
    }).setView([currentUserCoords.lat, currentUserCoords.lng], 15);

    window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(routeMap);

    if (!route.length) {
      routeMap.setView([currentUserCoords.lat, currentUserCoords.lng], 15);
      return;
    }

    const latLngs = route.map((point) => [point.latitude, point.longitude]);
    routePolyline = window.L.polyline(latLngs, {
      color: "#1d4ed8",
      weight: 4,
      opacity: 0.8
    }).addTo(routeMap);

    const startMarker = window.L.circleMarker(latLngs[0], {
      radius: 7,
      color: "#ffffff",
      weight: 2,
      fillColor: "#0e766e",
      fillOpacity: 1
    }).bindTooltip("Start", { permanent: true, direction: "top", offset: [0, -8] }).addTo(routeMap);

    const endMarker = window.L.circleMarker(latLngs[latLngs.length - 1], {
      radius: 7,
      color: "#ffffff",
      weight: 2,
      fillColor: "#b85b45",
      fillOpacity: 1
    }).bindTooltip("Latest", { permanent: true, direction: "top", offset: [0, -8] }).addTo(routeMap);

    routeMarkers.push(startMarker, endMarker);
    routeMap.fitBounds(routePolyline.getBounds(), { padding: [24, 24] });
    window.setTimeout(() => routeMap.invalidateSize(), 80);
  } catch (error) {
    feedback.textContent = error.message;
  }
}

function destroyRouteMap() {
  if (routeMap) {
    routeMap.remove();
    routeMap = null;
  }
  routePolyline = null;
  routeMarkers = [];
}

function renderManagerUsers() {
  const userList = document.getElementById("manager-user-list");
  if (!userList) {
    return;
  }

  const content = uiState.data.users
    .map((user, index) => {
      const userBookings = uiState.data.bookings.filter((booking) => booking.customer === user.name);
      const activeBookings = userBookings.filter((booking) => booking.status === "Active").length;
      const toggleId = `user-orders-toggle-${index}`;
      const bookingRows = userBookings.length
        ? userBookings
            .slice()
            .reverse()
            .map(
              (booking) => `
                <div class="user-entry__order">
                  <span>${booking.scooterId}</span>
                  <strong>${booking.startTime || "-"} to ${booking.endTime || "-"} / GBP ${booking.price} / ${booking.status}</strong>
                </div>
              `
            )
            .join("")
        : `<div class="user-entry__order"><span>No bookings</span><strong>This user has no booking records.</strong></div>`;
      return `
        <div class="user-entry" data-user-id="${user.id}">
          <div class="user-entry__summary">
            <div>
              <span>${user.name} / ${user.role}</span>
              <small>${userBookings.length} bookings, ${activeBookings} active</small>
            </div>
            <strong>${user.email}</strong>
            <label class="button button--ghost user-entry__toggle" for="${toggleId}">View orders</label>
          </div>
          <input type="checkbox" class="user-entry__toggle-input" id="${toggleId}">
          <div class="user-entry__orders">${bookingRows}</div>
        </div>
      `;
    })
    .join("");

  userList.innerHTML = content || "<div><span>No users found</span></div>";
}

function renderIssues() {
  const customerContent = uiState.data.issues
    .map(
      (issue) => `
        <div>
          <span>${issue.scooterId}: ${issue.description}</span>
          <strong>${issue.priority} / ${issue.status}</strong>
        </div>
      `
    )
    .join("");
  document.getElementById("issue-list").innerHTML = customerContent;

  const managerContent = uiState.data.issues
    .map(
      (issue) => `
        <div>
          <span>${issue.scooterId}: ${issue.description}</span>
          <strong>${issue.priority} / ${issue.status}</strong>
          ${issue.status === "Open" && issue.priority !== "High" ? `<button type="button" class="button button--ghost escalate-issue-button" data-issue-id="${issue.id}">Escalate</button>` : ""}
          ${issue.status === "Open" ? `<button type="button" class="button button--ghost resolve-issue-button" data-issue-id="${issue.id}">Resolve</button>` : ""}
        </div>
      `
    )
    .join("");
  document.getElementById("manager-issue-list").innerHTML = managerContent;

  const highPriorityContent = uiState.data.issues
    .filter((issue) => issue.priority === "High" && issue.status === "Open")
    .map(
      (issue) => `
        <div>
          <span>${issue.scooterId}: ${issue.description}</span>
          <strong>${issue.priority} / ${issue.status}</strong>
        </div>
      `
    )
    .join("");
  const highPriorityContainer = document.getElementById("manager-high-priority-issues");
  if (highPriorityContainer) {
    highPriorityContainer.innerHTML =
      highPriorityContent || "<div><span>No high priority issues</span><strong>Escalated issues will appear here.</strong></div>";
  }

  document.querySelectorAll(".resolve-issue-button").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const result = await api("/api/issues/resolve", {
          method: "POST",
          body: JSON.stringify({ issueId: Number(button.dataset.issueId) })
        });
        uiState.data = result.state;
        renderAll();
      } catch (error) {
        document.getElementById("booking-action-feedback").textContent = error.message;
      }
    });
  });

  document.querySelectorAll(".escalate-issue-button").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const result = await api("/api/issues/escalate", {
          method: "POST",
          body: JSON.stringify({ issueId: Number(button.dataset.issueId) })
        });
        uiState.data = result.state;
        renderAll();
      } catch (error) {
        document.getElementById("booking-action-feedback").textContent = error.message;
      }
    });
  });
}

function renderSummaries() {
  const summary = uiState.data.summary;
  document.getElementById("summary-available").textContent = summary.availableScooters;
  document.getElementById("summary-active").textContent = summary.activeBookings;
  document.getElementById("summary-revenue").textContent = `GBP ${summary.totalRevenue}`;
  document.getElementById("summary-issues").textContent = summary.openIssues;
  document.getElementById("manager-bookings").textContent = summary.totalBookings;
  document.getElementById("manager-revenue").textContent = `GBP ${summary.totalRevenue}`;
  document.getElementById("manager-availability").textContent = `${summary.fleetAvailability}%`;
  document.getElementById("manager-issue-count").textContent = summary.openIssues;
}

function buildBarChart(items, valueKey, labelKey, colorClass) {
  const maxValue = Math.max(...items.map((item) => item[valueKey] || 0), 1);
  return items
    .map((item) => {
      const value = item[valueKey] || 0;
      const width = Math.max(6, Math.round((value / maxValue) * 100));
      return `
        <div class="chart-row">
          <div class="chart-row__label">
            <strong>${item[labelKey]}</strong>
            <span>GBP ${value}</span>
          </div>
          <div class="chart-row__track">
            <div class="chart-row__bar ${colorClass}" style="width: ${width}%"></div>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderStatistics() {
  const optionSummary = document.getElementById("statistics-option-summary");
  const dailySummary = document.getElementById("statistics-daily-summary");
  const optionChart = document.getElementById("statistics-option-chart");
  const dailyChart = document.getElementById("statistics-daily-chart");
  if (!optionSummary || !dailySummary || !optionChart || !dailyChart) {
    return;
  }

  const optionData = uiState.data.statistics?.weeklyIncomeByOption || [];
  const dailyData = uiState.data.statistics?.dailyIncome || [];

  optionSummary.innerHTML = optionData
    .map(
      (entry) => `
        <div>
          <span>${entry.option}</span>
          <strong>GBP ${entry.income} / ${entry.bookings} booking(s)</strong>
        </div>
      `
    )
    .join("") || "<div><span>No weekly data</span><strong>Income will appear after bookings are created.</strong></div>";

  dailySummary.innerHTML = dailyData
    .map(
      (entry) => `
        <div>
          <span>${entry.date}</span>
          <strong>GBP ${entry.income} / ${entry.bookings} booking(s)</strong>
        </div>
      `
    )
    .join("") || "<div><span>No daily data</span><strong>Daily income will appear after bookings are created.</strong></div>";

  optionChart.innerHTML = buildBarChart(optionData, "income", "option", "chart-row__bar--accent");
  dailyChart.innerHTML = buildBarChart(dailyData, "income", "date", "chart-row__bar--warm");
}

function renderAll() {
  renderScooterSelects();
  syncGuestBookingDefaults();
  renderScooterMap();
  renderBookingFormDetails();
  renderBookingEstimate();
  renderBookingSummary();
  renderPriceConfiguration();
  renderBookingHistory();
  renderManagerUsers();
  renderManagerStoreOptions();
  renderManagerStoreInventory();
  renderManagerStoreMap();
  renderIssues();
  renderSummaries();
  renderStatistics();
}

authModeButtons.forEach((button) => {
  button.addEventListener("click", () => setAuthMode(button.dataset.authMode));
});

roleButtons.forEach((button) => {
  button.addEventListener("click", () => setRole(button.dataset.role));
});

tabs.forEach((tab) => {
  tab.addEventListener("click", () => setPage(tab.dataset.page));
});

managerNavTabs.forEach((tab) => {
  tab.addEventListener("click", () => setManagerSection(tab.dataset.managerSection));
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = document.getElementById("register-name").value.trim();
  const accountType = document.getElementById("register-account-type").value;
  const email = document.getElementById("register-email").value.trim();
  const password = document.getElementById("register-password").value.trim();

  try {
    const passwordHash = await hashClientPassword(password);
    const result = await api("/api/register", {
      method: "POST",
      body: JSON.stringify({ role: "customer", name, accountType, email, password: passwordHash })
    });
    registerForm.reset();
    authFeedback.textContent = `Account created for ${result.user.name}. You can now log in.`;
    setAuthMode("login");
    await loadState();
  } catch (error) {
    authFeedback.textContent = error.message;
  }
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value.trim();

  try {
    const passwordHash = await hashClientPassword(password);
    const result = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ role: uiState.role, email, password: passwordHash })
    });
    uiState.sessionToken = result.sessionToken;
    localStorage.setItem("cityhopSessionToken", result.sessionToken);
    loginForm.reset();
    await loadState();
    enterApp(result.user);
  } catch (error) {
    authFeedback.textContent = error.message;
  }
});

bookingForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const scooterId = uiState.selectedScooterId;
  const startTime = document.getElementById("booking-start-time").value;
  const endTime = document.getElementById("booking-end-time").value;
  const useSavedCard = document.getElementById("use-saved-card")?.checked;
  const payment = useSavedCard
    ? { useSavedCard: true }
    : {
        useSavedCard: false,
        cardholderName: document.getElementById("payment-cardholder").value.trim(),
        cardNumber: document.getElementById("payment-card-number").value.trim(),
        expiry: document.getElementById("payment-expiry").value.trim(),
        cvv: document.getElementById("payment-cvv").value.trim(),
        saveCard: document.getElementById("save-card-for-future").checked
      };

  if (!scooterId) {
    document.getElementById("booking-feedback").textContent = "Please choose a scooter from the map before booking.";
    return;
  }

  try {
    const result = await api("/api/bookings", {
      method: "POST",
      body: JSON.stringify({ scooterId, startTime, endTime, payment })
    });
    document.getElementById("booking-feedback").textContent = result.message;
    uiState.data = result.state;
    bookingForm.reset();
    uiState.selectedScooterId = "";
    renderAll();
    setPage("booking-history");
  } catch (error) {
    document.getElementById("booking-feedback").textContent = error.message;
  }
});

issueForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const scooterId = document.getElementById("issue-scooter").value;
  const description = document.getElementById("issue-description").value.trim();

  try {
    const result = await api("/api/issues", {
      method: "POST",
      body: JSON.stringify({ scooterId, description })
    });
    uiState.data = result.state;
    issueForm.reset();
    document.getElementById("issue-feedback").textContent = result.message;
    renderAll();
  } catch (error) {
    document.getElementById("issue-feedback").textContent = error.message;
  }
});

if (storeForm) {
  storeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const isEditing = Boolean(uiState.selectedManagerStoreId);
      const result = await api(isEditing ? "/api/stores/update" : "/api/stores", {
        method: "POST",
        body: JSON.stringify({
          ...(isEditing ? { storeId: uiState.selectedManagerStoreId } : {}),
          name: document.getElementById("store-name").value.trim(),
          latitude: Number(document.getElementById("store-latitude").value),
          longitude: Number(document.getElementById("store-longitude").value)
        })
      });
      uiState.data = result.state;
      resetStoreForm();
      document.getElementById("store-feedback").textContent = result.message;
      renderAll();
    } catch (error) {
      document.getElementById("store-feedback").textContent = error.message;
    }
  });
}

document.getElementById("store-cancel-edit-button")?.addEventListener("click", () => {
  resetStoreForm();
  document.getElementById("store-feedback").textContent = "Store editing was cancelled.";
});

document.getElementById("store-delete-button")?.addEventListener("click", async () => {
  if (!uiState.selectedManagerStoreId) {
    return;
  }

  try {
    const result = await api("/api/stores/delete", {
      method: "POST",
      body: JSON.stringify({ storeId: uiState.selectedManagerStoreId })
    });
    uiState.data = result.state;
    resetStoreForm();
    document.getElementById("store-feedback").textContent = result.message;
    document.getElementById("manager-scooter-feedback").textContent = "";
    renderAll();
  } catch (error) {
    document.getElementById("store-feedback").textContent = error.message;
  }
});

if (managerScooterForm) {
  managerScooterForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await api("/api/stores/scooters", {
        method: "POST",
        body: JSON.stringify({
          storeId: Number(document.getElementById("manager-store-select").value),
          hourlyPrice: Number(document.getElementById("manager-scooter-price").value),
          battery: Number(document.getElementById("manager-scooter-battery").value)
        })
      });
      uiState.data = result.state;
      managerScooterForm.reset();
      document.getElementById("manager-scooter-feedback").textContent = result.message;
      renderAll();
    } catch (error) {
      document.getElementById("manager-scooter-feedback").textContent = error.message;
    }
  });
}

document.getElementById("manager-store-select")?.addEventListener("change", () => {
  renderManagerStoreInventory();
});

document.getElementById("guest-store-select")?.addEventListener("change", () => {
  renderScooterSelects();
});

document.getElementById("use-saved-card")?.addEventListener("change", () => {
  updatePaymentFieldVisibility();
});

document.getElementById("guest-booking-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/staff/bookings", {
      method: "POST",
      body: JSON.stringify({
        guestName: document.getElementById("guest-name").value.trim(),
        guestEmail: document.getElementById("guest-email").value.trim(),
        scooterId: document.getElementById("guest-scooter-select").value,
        startTime: document.getElementById("guest-start-time").value,
        endTime: document.getElementById("guest-end-time").value,
        payment: {
          cardholderName: document.getElementById("guest-cardholder").value.trim(),
          cardNumber: document.getElementById("guest-card-number").value.trim(),
          expiry: document.getElementById("guest-card-expiry").value.trim(),
          cvv: document.getElementById("guest-card-cvv").value.trim()
        }
      })
    });
    uiState.data = result.state;
    event.target.reset();
    document.getElementById("guest-booking-feedback").textContent = result.message;
    renderAll();
  } catch (error) {
    document.getElementById("guest-booking-feedback").textContent = error.message;
  }
});

logoutButton.addEventListener("click", () => {
  logout();
});
backToProductsButton.addEventListener("click", () => setPage("products"));
document.getElementById("booking-start-time").addEventListener("input", () => renderBookingEstimate());
document.getElementById("booking-end-time").addEventListener("input", () => renderBookingEstimate());

async function bootstrap() {
  setRole("customer");
  setAuthMode("register");
  await loadState();
  renderAll();

  if (!uiState.sessionToken) {
    return;
  }

  try {
    const result = await api("/api/session");
    uiState.currentUser = result.user;
    enterApp(result.user);
    requestUserLocation();
  } catch (error) {
    uiState.sessionToken = "";
    localStorage.removeItem("cityhopSessionToken");
  }
}

bootstrap();


