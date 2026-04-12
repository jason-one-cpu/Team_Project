const uiState = {
  authMode: "register",
  role: "customer",
  currentUser: null,
  sessionToken: localStorage.getItem("cityhopSessionToken") || "",
  currentPage: "products",
  selectedScooterId: "",
  data: {
    users: [],
    scooters: [],
    bookings: [],
    issues: [],
    priceMap: {},
    summary: {
      availableScooters: 0,
      activeBookings: 0,
      totalBookings: 0,
      totalRevenue: 0,
      openIssues: 0,
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
const tabs = document.querySelectorAll(".tab");
const pages = document.querySelectorAll(".page");
const managerTab = document.querySelector('[data-page="manager"]');
const bookingForm = document.getElementById("booking-form");
const issueForm = document.getElementById("issue-form");
const priceForm = document.getElementById("price-form");
const logoutButton = document.getElementById("logout-button");
const backToProductsButton = document.getElementById("back-to-products-button");

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
    throw new Error("Backend API is not running. Please start the app with `python server.py` and open http://127.0.0.1:8000.");
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

function setAuthMode(mode) {
  uiState.authMode = mode;
  authModeButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.authMode === mode);
  });
  registerForm.classList.toggle("hidden", mode !== "register");
  loginForm.classList.toggle("hidden", mode !== "login");
  authTitle.textContent = mode === "register" ? "Create account" : "Sign in";
  authSubtitle.textContent = mode === "register"
    ? `Register a new ${uiState.role} account to enter the platform.`
    : `Login as a ${uiState.role} to continue into the platform.`;
  authFeedback.textContent = "Accounts are now handled through the SQLite-backed backend.";
}

function setRole(role) {
  uiState.role = role;
  roleButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.role === role);
  });
  authRoleLabel.textContent = "Customer Access";
  document.getElementById("login-button").textContent = "Login";
  setAuthMode(uiState.authMode);
}

function setPage(pageId) {
  uiState.currentPage = pageId;
  tabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.page === pageId);
  });
  pages.forEach((page) => {
    page.classList.toggle("is-active", page.id === `${pageId}-page`);
  });
}

function setBookingSelection(scooterId) {
  uiState.selectedScooterId = scooterId;
  const bookingSelect = document.getElementById("booking-scooter");
  if (bookingSelect && scooterId) {
    bookingSelect.value = scooterId;
  }
}

function enterApp(user) {
  uiState.currentUser = user;
  authScreen.classList.add("hidden");
  appShell.classList.remove("hidden");
  document.getElementById("welcome-text").textContent = `Welcome, ${user.name}`;
  document.getElementById("welcome-role").textContent = user.role === "manager" ? "Manager" : "Customer";
  document.getElementById("app-title").textContent = user.role === "manager" ? "Manager Portal" : "Customer Portal";
  managerTab.classList.toggle("hidden", user.role !== "manager");
  setPage(user.role === "manager" ? "manager" : "products");
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
  const bookingSelect = document.getElementById("booking-scooter");
  const issueSelect = document.getElementById("issue-scooter");
  const available = uiState.data.scooters.filter((scooter) => scooter.available);

  bookingSelect.innerHTML = available
    .map(
      (scooter) =>
        `<option value="${scooter.id}">${scooter.id} - ${scooter.location} (${scooter.battery}% battery)</option>`
    )
    .join("");

  if (uiState.selectedScooterId && available.some((scooter) => scooter.id === uiState.selectedScooterId)) {
    bookingSelect.value = uiState.selectedScooterId;
  }

  issueSelect.innerHTML = uiState.data.scooters
    .map((scooter) => `<option value="${scooter.id}">${scooter.id} - ${scooter.location}</option>`)
    .join("");
}

function renderFleet() {
  document.getElementById("fleet-grid").innerHTML = uiState.data.scooters
    .map(
      (scooter) => `
        <article class="fleet__item">
          <h3>${scooter.id}</h3>
          <p><strong>Location:</strong> ${scooter.location}</p>
          <p><strong>Battery:</strong> ${scooter.battery}%</p>
          <span class="status ${scooter.available ? "status--available" : "status--booked"}">
            ${scooter.available ? "Available" : "Booked"}
          </span>
          ${scooter.available ? `<div class="fleet__actions"><button type="button" class="button button--primary book-now-button" data-scooter-id="${scooter.id}">Book</button></div>` : ""}
        </article>
      `
    )
    .join("");

  document.querySelectorAll(".book-now-button").forEach((button) => {
    button.addEventListener("click", () => {
      setBookingSelection(button.dataset.scooterId);
      setPage("book");
    });
  });
}

function renderBookingSummary() {
  const summary = document.getElementById("booking-summary");
  const booking = [...uiState.data.bookings].reverse().find((item) => item.status === "Active") || uiState.data.bookings[uiState.data.bookings.length - 1];

  if (!booking) {
    summary.innerHTML = "<div><span>No booking yet</span><strong>Create your first hire</strong></div>";
    return;
  }

  summary.innerHTML = `
    <div><span>Customer</span><strong>${booking.customer}</strong></div>
    <div><span>Scooter</span><strong>${booking.scooterId}</strong></div>
    <div><span>Duration</span><strong>${booking.durationHours} hours</strong></div>
    <div><span>Cost</span><strong>GBP ${booking.price}</strong></div>
    <div><span>Status</span><strong>${booking.status}</strong></div>
  `;
}

function renderPriceConfiguration() {
  const priceMap = uiState.data.priceMap || {};
  const ids = ["1", "4", "24", "168"];
  ids.forEach((duration) => {
    const input = document.getElementById(`price-${duration}`);
    if (input) {
      input.value = priceMap[duration] ?? "";
    }
  });

  const durationSelect = document.getElementById("booking-duration");
  durationSelect.innerHTML = [
    { value: "1", label: "1 hour" },
    { value: "4", label: "4 hours" },
    { value: "24", label: "1 day" },
    { value: "168", label: "1 week" }
  ]
    .map((option) => `<option value="${option.value}">${option.label} - GBP ${priceMap[option.value] ?? "-"}</option>`)
    .join("");
}

function renderBookingHistory() {
  const customerContent = uiState.data.bookings
    .slice()
    .reverse()
    .map(
      (booking) => `
          <div>
            <span>${booking.customer} / ${booking.scooterId}</span>
            <strong>${booking.durationHours}h / GBP ${booking.price} / ${booking.status}</strong>
            ${booking.status === "Active" ? `<button type="button" class="button button--ghost history-end-button" data-booking-id="${booking.id}">End</button>` : ""}
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
            <strong>${booking.durationHours}h / GBP ${booking.price} / ${booking.status}</strong>
            ${booking.status === "Active" ? `<div class="fleet__actions"><button type="button" class="button button--ghost manager-end-booking-button" data-booking-id="${booking.id}">End</button><button type="button" class="button button--ghost manager-cancel-booking-button" data-booking-id="${booking.id}">Cancel</button></div>` : ""}
          </div>
        `
    )
    .join("");

  document.getElementById("customer-booking-history").innerHTML = customerContent;
  document.getElementById("booking-history").innerHTML = managerContent;

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
}

function renderManagerUsers() {
  const content = uiState.data.users
    .map((user) => {
      const userBookings = uiState.data.bookings.filter((booking) => booking.customer === user.name);
      const activeBookings = userBookings.filter((booking) => booking.status === "Active").length;
      return `
        <div>
          <span>${user.name} / ${user.role}</span>
          <strong>${user.email}</strong>
          <small>${userBookings.length} bookings, ${activeBookings} active</small>
        </div>
      `;
    })
    .join("");

  document.getElementById("manager-user-list").innerHTML = content || "<div><span>No users found</span></div>";
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
          ${issue.status === "Open" ? `<button type="button" class="button button--ghost resolve-issue-button" data-issue-id="${issue.id}">Resolve</button>` : ""}
        </div>
      `
    )
    .join("");
  document.getElementById("manager-issue-list").innerHTML = managerContent;

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

function renderAll() {
  renderScooterSelects();
  renderFleet();
  renderBookingSummary();
  renderPriceConfiguration();
  renderBookingHistory();
  renderManagerUsers();
  renderIssues();
  renderSummaries();
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

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = document.getElementById("register-name").value.trim();
  const email = document.getElementById("register-email").value.trim();
  const password = document.getElementById("register-password").value.trim();

  try {
    const result = await api("/api/register", {
      method: "POST",
      body: JSON.stringify({ role: "customer", name, email, password })
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
    const result = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ role: "customer", email, password })
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
  const scooterId = document.getElementById("booking-scooter").value;
  const durationHours = Number(document.getElementById("booking-duration").value);

  try {
    const result = await api("/api/bookings", {
      method: "POST",
      body: JSON.stringify({ scooterId, durationHours })
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
    renderAll();
  } catch (error) {
    document.getElementById("booking-action-feedback").textContent = error.message;
  }
});

priceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const prices = {
    1: Number(document.getElementById("price-1").value),
    4: Number(document.getElementById("price-4").value),
    24: Number(document.getElementById("price-24").value),
    168: Number(document.getElementById("price-168").value)
  };

  try {
    const result = await api("/api/prices", {
      method: "POST",
      body: JSON.stringify({ prices })
    });
    uiState.data = result.state;
    document.getElementById("price-feedback").textContent = result.message;
    renderAll();
  } catch (error) {
    document.getElementById("price-feedback").textContent = error.message;
  }
});

logoutButton.addEventListener("click", () => {
  logout();
});
backToProductsButton.addEventListener("click", () => setPage("products"));

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
  } catch (error) {
    uiState.sessionToken = "";
    localStorage.removeItem("cityhopSessionToken");
  }
}

bootstrap();
