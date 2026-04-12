const state = {
  users: [
    { id: "U-001", name: "Demo User", email: "demo@cityhop.app" }
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

const tabs = document.querySelectorAll(".tab");
const tabTargets = document.querySelectorAll("[data-tab-target]");
const views = document.querySelectorAll(".view");
const registerForm = document.getElementById("register-form");
const bookingForm = document.getElementById("booking-form");
const issueForm = document.getElementById("issue-form");
const loginForm = document.getElementById("login-form");

const dataService = {
  getState() {
    return structuredClone(state);
  },
  createUser({ name, email }) {
    const user = {
      id: `U-${String(state.users.length + 1).padStart(3, "0")}`,
      name,
      email
    };
    state.users.push(user);
    return user;
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
      return null;
    }

    const issue = {
      scooterId,
      description,
      priority: description.toLowerCase().includes("brake") ? "High" : "Medium"
    };
    state.issues.unshift(issue);
    return issue;
  }
};

function switchTab(targetId) {
  tabs.forEach((tab) => tab.classList.toggle("is-active", tab.dataset.tab === targetId));
  views.forEach((view) => view.classList.toggle("is-active", view.id === targetId));
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

tabTargets.forEach((button) => {
  button.addEventListener("click", () => switchTab(button.dataset.tabTarget));
});

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
  const fleetGrid = document.getElementById("fleet-grid");
  fleetGrid.innerHTML = state.scooters
    .map(
      (scooter) => `
        <div class="fleet__item">
          <h3>${scooter.id}</h3>
          <p><strong>Location:</strong> ${scooter.location}</p>
          <p><strong>Battery:</strong> ${scooter.battery}%</p>
          <span class="status ${scooter.available ? "status--available" : "status--booked"}">
            ${scooter.available ? "Available" : "Booked"}
          </span>
        </div>
      `
    )
    .join("");
}

function renderBookingSummary() {
  const summary = document.getElementById("booking-summary");
  const booking = state.bookings[state.bookings.length - 1];

  if (!booking) {
    summary.innerHTML = "<div><span>No active booking yet.</span></div>";
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

function renderCustomerHistory() {
  const history = document.getElementById("customer-booking-history");
  history.innerHTML = state.bookings
    .slice()
    .reverse()
    .map(
      (booking, index) => `
        <div>
          <span>${index === 0 ? "Latest booking" : "Previous booking"}</span>
          <strong>${booking.customer} / ${booking.scooterId} / ${booking.durationHours}h / GBP ${booking.price}</strong>
        </div>
      `
    )
    .join("");
}

function renderManager() {
  const totalRevenue = state.bookings.reduce((sum, booking) => sum + booking.price, 0);
  const availableCount = state.scooters.filter((scooter) => scooter.available).length;
  const fleetAvailability = Math.round((availableCount / state.scooters.length) * 100);

  document.getElementById("summary-available").textContent = availableCount;
  document.getElementById("summary-active").textContent = state.bookings.filter((booking) => booking.status === "Active").length;
  document.getElementById("summary-revenue").textContent = `GBP ${totalRevenue}`;
  document.getElementById("summary-issues").textContent = state.issues.length;

  document.getElementById("manager-bookings").textContent = state.bookings.length;
  document.getElementById("manager-revenue").textContent = `GBP ${totalRevenue}`;
  document.getElementById("manager-availability").textContent = `${fleetAvailability}%`;
  document.getElementById("manager-issue-count").textContent = state.issues.length;

  document.getElementById("booking-history").innerHTML = state.bookings
    .map(
      (booking) => `
        <div>
          <span>${booking.customer}</span>
          <strong>${booking.scooterId} / ${booking.durationHours}h / GBP ${booking.price}</strong>
        </div>
      `
    )
    .join("");

  document.getElementById("issue-list").innerHTML = state.issues
    .map(
      (issue) => `
        <div>
          <span>${issue.scooterId}: ${issue.description}</span>
          <strong>${issue.priority}</strong>
        </div>
      `
    )
    .join("");
}

function renderAll() {
  renderScooterSelects();
  renderFleet();
  renderBookingSummary();
  renderCustomerHistory();
  renderManager();
}

registerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const name = document.getElementById("register-name").value.trim();
  const email = document.getElementById("register-email").value.trim();

  if (!name || !email) {
    document.getElementById("register-feedback").textContent = "Please enter both name and email.";
    return;
  }

  const user = dataService.createUser({ name, email });
  registerForm.reset();
  document.getElementById("register-feedback").textContent = `Account created locally for ${user.name}.`;
});

loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const email = document.getElementById("login-email").value.trim();
  const exists = dataService.getState().users.some((user) => user.email === email);
  document.getElementById("login-feedback").textContent = exists
    ? "Login interaction recorded for frontend demo."
    : "No matching demo account found. Create one above first.";
});

bookingForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const customerName = document.getElementById("customer-name").value.trim();
  const scooterId = document.getElementById("booking-scooter").value;
  const durationHours = Number(document.getElementById("booking-duration").value);
  const result = dataService.createBooking({
    customer: customerName,
    scooterId,
    durationHours
  });

  if (!result.ok) {
    document.getElementById("booking-feedback").textContent = result.message;
    return;
  }

  bookingForm.reset();
  document.getElementById("booking-feedback").textContent = result.message;
  renderAll();
});

issueForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const scooterId = document.getElementById("issue-scooter").value;
  const description = document.getElementById("issue-description").value.trim();

  if (!description) {
    return;
  }

  dataService.createIssue({
    scooterId,
    description
  });

  issueForm.reset();
  renderAll();
});

renderAll();
