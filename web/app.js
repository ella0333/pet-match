const view = document.getElementById("view");
const modal = document.getElementById("modal");

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch { /* not JSON */ }
    throw new Error(msg);
  }
  return r.json();
}

function initials(name) {
  return esc(name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase());
}

function when(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function photoGrid(photos) {
  if (!photos.length) return "";
  return `<div class="photos">${photos.map((p) => `
    <figure><img src="${esc(p.url)}" alt="" loading="lazy">
    ${p.credit ? `<figcaption><a href="${esc(p.credit.page)}" target="_blank" rel="noopener">${esc(p.credit.author || "Wikimedia Commons")}, ${esc(p.credit.license)}</a></figcaption>` : ""}
    </figure>`).join("")}</div>`;
}

function messageButton(p) {
  return p.can_message
    ? `<button class="btn primary" data-message="${esc(p.poster)}">&#128172; Message ${esc(p.poster)}</button>`
    : "";
}

function postCard(p) {
  return `<article class="card">
    <div class="post-head">
      <div class="avatar">${initials(p.poster)}</div>
      <div>
        <h3>${esc(p.poster)} <span class="tag ${esc(p.post_type)}">${esc(p.post_type)}</span></h3>
        <div class="muted">Posted in <strong>${esc(p.group)}</strong> &middot; ${when(p.created_at)}</div>
      </div>
    </div>
    <div>${esc(p.text)}</div>
    ${photoGrid(p.photos)}
    <div class="actions">${messageButton(p)}</div>
  </article>`;
}

function bar(v) {
  return `<span class="bar"><i style="width:${Math.round(v * 100)}%"></i></span>`;
}

function matchCard(m) {
  const p = m.post;
  const v = m.verdict;
  const pct = v ? v.same_pet_likelihood : Math.round(m.combined * 100);
  const cls = pct >= 70 ? "high" : pct >= 40 ? "mid" : "low";
  const lead = p.photos[0];
  const facts = [];
  if (m.gap_km !== null) facts.push(m.gap_km === 0 ? "same area" : `${m.gap_km} km apart`);
  if (m.days !== null) facts.push(m.days >= 0 ? `${m.days} day${m.days === 1 ? "" : "s"} between lost and found` : "dates overlap");
  return `<article class="card match">
    <div class="lead">${lead ? `<img src="${esc(lead.url)}" alt="">` : ""}</div>
    <div>
      <div class="likelihood ${cls}">${v ? `${pct}% likely the same pet` : `${pct}% similar by photo and details`}</div>
      ${v ? `<div>${esc(v.summary)}</div>
        <div class="chips">${v.matching_features.map((f) => `<span class="chip">${esc(f)}</span>`).join("")}
        ${v.conflicts.map((f) => `<span class="chip conflict">${esc(f)}</span>`).join("")}</div>` : ""}
      <div class="muted"><span class="tag ${esc(p.post_type)}">${esc(p.post_type)}</span>
        ${esc(p.location)}${p.event_date ? ` &middot; ${esc(p.event_date)}` : ""}${facts.length ? ` &middot; ${facts.join(" &middot; ")}` : ""}</div>
      <div class="not-member">Posted in ${esc(p.group)} by ${esc(p.poster)}. You don't need to join the group to see it.</div>
      <p>${esc(p.text)}</p>
      ${photoGrid(p.photos.slice(1))}
      <div class="scores">
        <span>Photo ${bar(m.scores.photo)}</span>
        <span>Description ${bar(m.scores.description)}</span>
        <span>Distance ${bar(m.scores.distance)}</span>
        <span>Timing ${bar(m.scores.time)}</span>
      </div>
      <div class="actions">${messageButton(p)}</div>
    </div>
  </article>`;
}

// Views -----------------------------------------------------------------------

function showSearch(kind) {
  const lost = kind === "lost";
  view.innerHTML = `<form class="card" id="search-form">
    <h2>${lost ? "I lost a pet" : "I found a pet"}</h2>
    <p class="muted">${lost
      ? "Add a photo of your pet. Before you post, we'll check found pet posts in every participating group, even ones you haven't joined."
      : "Add a photo of the pet you found. Before you post, we'll check lost pet posts in every participating group, even ones you haven't joined."}</p>
    <input type="hidden" name="post_type" value="${lost ? "lost" : "found"}">
    <div class="row"><label for="photos">Photos</label>
      <input type="file" id="photos" name="photos" accept="image/*" multiple required></div>
    <div class="row"><label for="details">Where and when (optional)</label>
      <textarea id="details" name="details" placeholder="${lost
        ? "For example: slipped out near Pine Street in Old Mill on Saturday, grey tabby with a white chest."
        : "For example: found near the park in Riverside this morning, no collar."}"></textarea></div>
    <div class="actions"><button class="btn primary" type="submit">Search for matches</button></div>
    <div id="search-status" class="muted status"></div>
    <p id="limits" class="muted"></p>
  </form>
  <div id="results"></div>`;
  api("/api/limits").then((l) => {
    if (!l.hosted) return;
    const el = document.getElementById("limits");
    if (!el) return;
    el.textContent = l.search_open
      ? `To keep this public demo affordable, each visitor can run ${l.searches_left_today} more search${l.searches_left_today === 1 ? "" : "es"} today. Need a photo to try? Use Download test photos in the menu.`
      : "Searching is paused on this demo for today, but you can still browse nearby posts.";
  }).catch(() => {});
  document.getElementById("search-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector("button[type=submit]");
    const status = document.getElementById("search-status");
    const results = document.getElementById("results");
    btn.disabled = true;
    results.innerHTML = "";
    status.innerHTML = `<span class="spinner"></span> Finding the pet in your photo and checking every participating group. This takes about half a minute.`;
    try {
      const res = await api("/api/search", { method: "POST", body: new FormData(form) });
      status.textContent = "";
      const n = res.matches.length;
      results.innerHTML = `<div class="card"><h2>${n ? `${n} possible match${n === 1 ? "" : "es"}` : "No matches yet"}</h2>
        <div class="muted">${esc(res.query.summary)}</div></div>
        ${res.matches.map(matchCard).join("")}
        <div class="card"><h3>Not here?</h3>
          <p class="muted">Post it and we'll keep checking. New ${lost ? "found" : "lost"} posts in every participating group are compared with yours, and you're notified when one matches.</p>
          <button class="btn primary" id="mock-post">Post to Lost and Found Pets</button></div>`;
      document.getElementById("mock-post").addEventListener("click", () => {
        openModal(`<h3>Posting is simulated</h3>
          <p class="muted">In the real feature, your post would be shared to every participating group near you,
          and you'd be notified when a matching post appears. This demo doesn't save anything you upload.</p>`);
      });
    } catch (err) {
      status.textContent = err.message;
    }
    btn.disabled = false;
  });
}

async function showFeed() {
  view.innerHTML = `<div class="card"><h2>Nearby lost and found posts</h2>
    <div class="muted">From every group that has opted in, whether or not you're a member.</div></div>
    <div class="empty"><span class="spinner"></span></div>`;
  const posts = await api("/api/feed");
  view.innerHTML = view.firstElementChild.outerHTML +
    (posts.length ? posts.map(postCard).join("") : `<div class="card empty">No posts yet.</div>`);
}

async function showOptIn() {
  const g = await api("/api/opt-in-demo");
  view.innerHTML = `<div class="card">
      <div class="eyebrow">Opt-in demo: a group page as its admin sees it</div>
      <h2>${esc(g.name)}</h2>
      <div class="muted">${esc(g.area)} &middot; ${g.members.toLocaleString()} members</div>
    </div>
    <div class="card">
      <div class="optin-row">
        <div><h3>Share lost and found posts with Lost and Found Pets</h3>
          <div class="muted">When this is on, anyone can find this group's lost and found pet posts in search and nearby posts without joining the group.</div></div>
        <label class="switch"><input type="checkbox" id="opt-in" ${g.opted_in ? "checked" : ""}><span></span></label>
      </div>
      <div id="opt-status" class="muted optin-status"></div>
    </div>
    ${g.posts.map(postCard).join("")}`;
  document.getElementById("opt-in").addEventListener("change", async (e) => {
    const status = document.getElementById("opt-status");
    try {
      await api("/api/opt-in-demo", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ opted_in: e.target.checked }),
      });
      status.textContent = e.target.checked
        ? "This group's posts now appear in Nearby posts and in search results."
        : "This group's posts no longer appear in Nearby posts or search results.";
    } catch (err) {
      status.textContent = err.message;
      e.target.checked = !e.target.checked;
    }
  });
}

function openModal(html) {
  document.getElementById("modal-body").innerHTML = html;
  modal.classList.remove("hidden");
}

async function route() {
  const name = location.hash.slice(1) || "found";
  document.querySelectorAll(".sidebar a[data-view]").forEach((a) =>
    a.classList.toggle("active", a.dataset.view === name));
  try {
    if (name === "lost" || name === "found") showSearch(name);
    else if (name === "optin") await showOptIn();
    else await showFeed();
  } catch (err) {
    view.innerHTML = `<div class="card empty">Couldn't load this page: ${esc(err.message)}</div>`;
  }
}

document.addEventListener("click", (e) => {
  const msg = e.target.closest("[data-message]");
  if (msg) {
    openModal(`<h3>Message ${esc(msg.dataset.message)}</h3>
      <p class="muted">In the real feature this opens a Messenger chat with ${esc(msg.dataset.message)},
      with their post attached so they know which pet you mean. Their phone number and email stay private.</p>`);
  }
});
document.getElementById("modal-close").addEventListener("click", () => modal.classList.add("hidden"));
window.addEventListener("hashchange", route);
route();
