const state = {
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
const bookingForm = document.getElementById("booking-form");
const issueForm = document.getElementById("issue-form");
const loginForm = document.getElementById("login-form");

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
  renderManager();
}

loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  document.getElementById("login-feedback").textContent = "Login interaction recorded for frontend demo.";
});

bookingForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const customerName = document.getElementById("customer-name").value.trim();
  const scooterId = document.getElementById("booking-scooter").value;
  const durationHours = Number(document.getElementById("booking-duration").value);
  const scooter = state.scooters.find((item) => item.id === scooterId);

  if (!customerName || !scooter || !scooter.available) {
    document.getElementById("booking-feedback").textContent = "Please choose an available scooter and enter a customer name.";
    return;
  }

  scooter.available = false;
  state.bookings.push({
    customer: customerName,
    scooterId,
    durationHours,
    price: state.priceMap[durationHours],
    status: "Active"
  });

  bookingForm.reset();
  document.getElementById("booking-feedback").textContent = `Booking created for ${customerName}.`;
  renderAll();
});

issueForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const scooterId = document.getElementById("issue-scooter").value;
  const description = document.getElementById("issue-description").value.trim();

  if (!description) {
    return;
  }

  state.issues.unshift({
    scooterId,
    description,
    priority: description.toLowerCase().includes("brake") ? "High" : "Medium"
  });

  issueForm.reset();
  renderAll();
});

renderAll();
