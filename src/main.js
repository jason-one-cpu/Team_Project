const state = {
  users: [
    { id: "U-001", role: "customer", name: "Demo User", email: "demo@cityhop.app" },
    { id: "M-001", role: "manager", name: "Operations Lead", email: "manager@cityhop.app" }
  ],
  scooters: [
    { id: "SC-101", location: "City Square", battery: 88, available: true },
    { id: "SC-102", location: "Train Station", battery: 74, available: true },
    { id: "SC-103", location: "Riverside", battery: 59, available: false },
    { id: "SC-104", location: "University Hub", battery: 93, available: true },
    { id: "SC-105", location: "Museum Lane", battery: 67, available: true }
  ],
  bookings: [
    {
      customer: "Demo User",
      scooterId: "SC-103",
      durationHours: 4,
      price: 12,
      status: "Active"
    }
  ],
  issues: [
    {
      scooterId: "SC-103",
      description: "Front light is flickering during evening use.",
      priority: "High"
    }
  ],
  priceMap: {
    1: 4,
    4: 12,
    24: 20,
    168: 60
  }
};

const uiState = {
  authMode: "register",
  role: "customer",
  currentUser: null,
  currentPage: "products"
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
const endBookingButton = document.getElementById("end-booking-button");
const cancelBookingButton = document.getElementById("cancel-booking-button");
const logoutButton = document.getElementById("logout-button");

const dataService = {
  createUser({ role, name, email }) {
    const prefix = role === "manager" ? "M" : "U";
    const user = {
      id: `${prefix}-${String(state.users.length + 1).padStart(3, "0")}`,
      role,
      name,
      email
    };
    state.users.push(user);
    return user;
  },
  findUserByEmail(email, role) {
    return state.users.find((user) => user.email === email && user.role === role);
  },
  createBooking({ customer, scooterId, durationHours }) {
    const scooter = state.scooters.find((item) => item.id === scooterId);
    if (!customer || !scooter || !scooter.available) {
      return { ok: false, message: "Please choose an available scooter and enter a customer name." };
    }

    scooter.available = false;
    const booking = {
      customer,
      scooterId,
      durationHours,
      price: state.priceMap[durationHours],
      status: "Active"
    };
    state.bookings.push(booking);
    return { ok: true, message: `Booking created for ${customer}.`, booking };
  },
  createIssue({ scooterId, description }) {
    if (!description) {
      return { ok: false };
    }
    state.issues.unshift({
      scooterId,
      description,
      priority: description.toLowerCase().includes("brake") ? "High" : "Medium"
    });
    return { ok: true };
  },
  updateLatestBookingStatus(nextStatus) {
    const activeBooking = [...state.bookings].reverse().find((booking) => booking.status === "Active");
    if (!activeBooking) {
      return { ok: false, message: "No active booking is available." };
    }

    activeBooking.status = nextStatus;
    const scooter = state.scooters.find((item) => item.id === activeBooking.scooterId);
    if (scooter) {
      scooter.available = true;
    }

    return {
      ok: true,
      message: nextStatus === "Completed"
        ? `Booking for ${activeBooking.customer} has been ended.`
        : `Booking for ${activeBooking.customer} has been cancelled.`
    };
  }
};

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
  authFeedback.textContent = "This is a local frontend prototype. Accounts are stored in demo memory.";
}

function setRole(role) {
  uiState.role = role;
  roleButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.role === role);
  });
  authRoleLabel.textContent = role === "manager" ? "Manager Access" : "Customer Access";
  document.getElementById("login-button").textContent = role === "manager" ? "Login as manager" : "Login";
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

function logout() {
  uiState.currentUser = null;
  appShell.classList.add("hidden");
  authScreen.classList.remove("hidden");
  setAuthMode("login");
}

function renderScooterSelects() {
  const bookingSelect = document.getElementById("booking-scooter");
  const issueSelect = document.getElementById("issue-scooter");
  const available = state.scooters.filter((scooter) => scooter.available);

  bookingSelect.innerHTML = available
    .map(
      (scooter) =>
        `<option value="${scooter.id}">${scooter.id} - ${scooter.location} (${scooter.battery}% battery)</option>`
    )
    .join("");

  issueSelect.innerHTML = state.scooters
    .map((scooter) => `<option value="${scooter.id}">${scooter.id} - ${scooter.location}</option>`)
    .join("");
}

function renderFleet() {
  document.getElementById("fleet-grid").innerHTML = state.scooters
    .map(
      (scooter) => `
        <article class="fleet__item">
          <h3>${scooter.id}</h3>
          <p><strong>Location:</strong> ${scooter.location}</p>
          <p><strong>Battery:</strong> ${scooter.battery}%</p>
          <span class="status ${scooter.available ? "status--available" : "status--booked"}">
            ${scooter.available ? "Available" : "Booked"}
          </span>
        </article>
      `
    )
    .join("");
}

function renderBookingSummary() {
  const summary = document.getElementById("booking-summary");
  const booking = [...state.bookings].reverse().find((item) => item.status === "Active") || state.bookings[state.bookings.length - 1];

  if (!booking) {
    summary.innerHTML = "<div><span>No booking yet</span><strong>Create your first hire</strong></div>";
    endBookingButton.disabled = true;
    cancelBookingButton.disabled = true;
    return;
  }

  summary.innerHTML = `
    <div><span>Customer</span><strong>${booking.customer}</strong></div>
    <div><span>Scooter</span><strong>${booking.scooterId}</strong></div>
    <div><span>Duration</span><strong>${booking.durationHours} hours</strong></div>
    <div><span>Cost</span><strong>GBP ${booking.price}</strong></div>
    <div><span>Status</span><strong>${booking.status}</strong></div>
  `;

  const isActive = booking.status === "Active";
  endBookingButton.disabled = !isActive;
  cancelBookingButton.disabled = !isActive;
}

function renderBookingHistory() {
  const content = state.bookings
    .slice()
    .reverse()
    .map(
      (booking) => `
        <div>
          <span>${booking.customer}</span>
          <strong>${booking.scooterId} / ${booking.durationHours}h / GBP ${booking.price} / ${booking.status}</strong>
        </div>
      `
    )
    .join("");
  document.getElementById("customer-booking-history").innerHTML = content;
  document.getElementById("booking-history").innerHTML = content;
}

function renderIssues() {
  const content = state.issues
    .map(
      (issue) => `
        <div>
          <span>${issue.scooterId}: ${issue.description}</span>
          <strong>${issue.priority}</strong>
        </div>
      `
    )
    .join("");
  document.getElementById("issue-list").innerHTML = content;
  document.getElementById("manager-issue-list").innerHTML = content;
}

function renderSummaries() {
  const totalRevenue = state.bookings.reduce((sum, booking) => sum + booking.price, 0);
  const availableCount = state.scooters.filter((scooter) => scooter.available).length;
  const activeCount = state.bookings.filter((booking) => booking.status === "Active").length;
  const fleetAvailability = Math.round((availableCount / state.scooters.length) * 100);

  document.getElementById("summary-available").textContent = availableCount;
  document.getElementById("summary-active").textContent = activeCount;
  document.getElementById("summary-revenue").textContent = `GBP ${totalRevenue}`;
  document.getElementById("summary-issues").textContent = state.issues.length;

  document.getElementById("manager-bookings").textContent = state.bookings.length;
  document.getElementById("manager-revenue").textContent = `GBP ${totalRevenue}`;
  document.getElementById("manager-availability").textContent = `${fleetAvailability}%`;
  document.getElementById("manager-issue-count").textContent = state.issues.length;
}

function renderAll() {
  renderScooterSelects();
  renderFleet();
  renderBookingSummary();
  renderBookingHistory();
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

registerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const name = document.getElementById("register-name").value.trim();
  const email = document.getElementById("register-email").value.trim();
  if (!name || !email) {
    authFeedback.textContent = "Please complete all required fields.";
    return;
  }
  const user = dataService.createUser({ role: uiState.role, name, email });
  registerForm.reset();
  authFeedback.textContent = `Account created for ${user.name}. You can now log in.`;
  setAuthMode("login");
});

loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const email = document.getElementById("login-email").value.trim();
  const user = dataService.findUserByEmail(email, uiState.role);
  if (!user) {
    authFeedback.textContent = `No ${uiState.role} account found for that email.`;
    return;
  }
  loginForm.reset();
  enterApp(user);
});

bookingForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const customer = document.getElementById("customer-name").value.trim() || uiState.currentUser?.name || "";
  const scooterId = document.getElementById("booking-scooter").value;
  const durationHours = Number(document.getElementById("booking-duration").value);
  const result = dataService.createBooking({ customer, scooterId, durationHours });
  document.getElementById("booking-feedback").textContent = result.message;
  if (result.ok) {
    bookingForm.reset();
    renderAll();
  }
});

issueForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const scooterId = document.getElementById("issue-scooter").value;
  const description = document.getElementById("issue-description").value.trim();
  const result = dataService.createIssue({ scooterId, description });
  if (!result.ok) {
    return;
  }
  issueForm.reset();
  renderAll();
});

endBookingButton.addEventListener("click", () => {
  const result = dataService.updateLatestBookingStatus("Completed");
  document.getElementById("booking-action-feedback").textContent = result.message;
  renderAll();
});

cancelBookingButton.addEventListener("click", () => {
  const result = dataService.updateLatestBookingStatus("Cancelled");
  document.getElementById("booking-action-feedback").textContent = result.message;
  renderAll();
});

logoutButton.addEventListener("click", logout);

setRole("customer");
setAuthMode("register");
renderAll();
