const csrf = document.querySelector('input[name="csrf"]').value;

async function refreshStatus() {
  const res = await fetch("/status", {credentials: "same-origin"});
  const data = await res.json();
  const dl = document.getElementById("status");
  dl.innerHTML = "";
  const rows = [
    ["HEAD", data.head || "(none)"],
    ["Outstanding candidates", String(data.outstanding)],
    ["Approved offerings", (data.approved_offerings || []).join(", ") || "(none)"],
    ["Directory memberships", (data.memberships || []).join(", ") || "(none)"],
    ["Decision saved at", data.decision_saved_at || "not yet"],
    ["Last published release", data.last_published_release_id || "not published"],
  ];
  for (const [k, v] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = v;
    dl.append(dt, dd);
  }
}

function show(payload) {
  document.getElementById("result").textContent = JSON.stringify(payload, null, 2);
}

document.getElementById("upload").addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = new FormData(event.target);
  const res = await fetch("/upload", {
    method: "POST",
    body,
    credentials: "same-origin",
    headers: {"X-CSRF-Token": csrf},
  });
  const data = await res.json();
  show(data);
  await refreshStatus();
});

document.getElementById("publish").addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = new FormData(event.target);
  const res = await fetch("/publish", {
    method: "POST",
    body,
    credentials: "same-origin",
    headers: {"X-CSRF-Token": csrf},
  });
  const data = await res.json();
  show(data);
  await refreshStatus();
});

refreshStatus().catch((err) => {
  document.getElementById("status").textContent = String(err);
});
