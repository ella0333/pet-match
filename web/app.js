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

function postCard(p, { showFind = true } = {}) {
  return `<article class="card">
    <div class="post-head">
      <div class="avatar">${initials(p.poster)}</div>
      <div>
        <h3>${esc(p.poster)} <span class="tag ${esc(p.post_type)}">${esc(p.post_type)}</span></h3>
        <div class="muted">${esc(p.group)} &middot; ${when(p.created_at)}</div>
      </div>
    </div>
    <div>${esc(p.text)}</div>
    ${photoGrid(p.photos)}
    ${showFind ? `<div class="actions"><a class="btn primary" href="#matches/${p.id}">Find possible matches</a></div>` : ""}
  </article>`;
}

function contactButtons(c, poster) {
  const out = [];
  if (c.messenger) out.push(`<button class="btn primary" data-message="${esc(c.messenger)}" data-poster="${esc(poster)}">&#128172; Message</button>`);
  if (c.phone) out.push(`<a class="btn" href="tel:${esc(c.phone)}">&#128222; ${esc(c.phone)}</a>`);
  if (c.email) out.push(`<a class="btn" href="mailto:${esc(c.email)}">&#9993;&#65039; Email</a>`);
  return out.join("");
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
      <div class="not-member">From ${esc(p.group)}. You don't need to join to see this.</div>
      <p>${esc(p.text)}</p>
      ${photoGrid(p.photos.slice(1))}
      <div class="scores">
        <span>Photo ${bar(m.scores.photo)}</span>
        <span>Description ${bar(m.scores.description)}</span>
        <span>Distance ${bar(m.scores.distance)}</span>
        <span>Timing ${bar(m.scores.time)}</span>
      </div>
      <div class="actions">${contactButtons(p.contact, p.poster)}</div>
    </div>
  </article>`;
}

// Views -----------------------------------------------------------------------

async function showFeed() {
  view.innerHTML = `<div class="card"><h2>Nearby lost and found posts</h2>
    <div class="muted">From every participating group, whether or not you're a member.</div></div>
    <div class="empty"><span class="spinner"></span></div>`;
  const posts = await api("/api/feed");
  view.innerHTML = view.firstElementChild.outerHTML +
    (posts.length ? posts.map((p) => postCard(p)).join("") : `<div class="card empty">No posts yet.</div>`);
}

function showReport() {
  view.innerHTML = `<form class="card" id="report-form">
    <h2>Report a lost or found pet</h2>
    <p class="muted">Write it the way you would in a group post. We'll search every participating group for you.</p>
    <div class="row toggle-type">
      <label><input type="radio" name="post_type" value="lost" checked><span>I lost a pet</span></label>
      <label><input type="radio" name="post_type" value="found"><span>I found a pet</span></label>
    </div>
    <div class="row"><label for="photos">Photos</label>
      <input type="file" id="photos" name="photos" accept="image/*" multiple required></div>
    <div class="row"><label for="text">Details</label>
      <textarea id="text" name="text" required placeholder="What they look like, where and when they went missing or were found, anything distinctive."></textarea></div>
    <div class="row"><label for="poster">Your name</label>
      <input type="text" id="poster" name="poster" value="You"></div>
    <div class="row"><label>How people can reach you</label>
      <div class="grid3">
        <input type="text" name="messenger" placeholder="Messenger name">
        <input type="tel" name="phone" placeholder="Phone">
        <input type="email" name="email" placeholder="Email">
      </div></div>
    <div class="actions"><button class="btn primary" type="submit">Post and search</button>
      <span id="report-status" class="muted"></span></div>
    <p id="limits" class="muted"></p>
  </form>`;
  api("/api/limits").then((l) => {
    if (!l.hosted) return;
    const el = document.getElementById("limits");
    if (!el) return;
    el.textContent = l.posting_open
      ? `To keep this public demo affordable, each visitor can add ${l.posts_left_today} more post${l.posts_left_today === 1 ? "" : "s"} today. Searching is unlimited.`
      : "New posts are paused on this demo for today, but you can still browse and search every group.";
  }).catch(() => {});
  document.getElementById("report-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector("button[type=submit]");
    const status = document.getElementById("report-status");
    btn.disabled = true;
    status.innerHTML = `<span class="spinner"></span> Reading your post and finding your pet in the photos...`;
    try {
      const { id } = await api("/api/posts", { method: "POST", body: new FormData(form) });
      location.hash = `#matches/${id}`;
    } catch (err) {
      status.textContent = err.message;
      btn.disabled = false;
    }
  });
}

async function showMatches(id) {
  const post = await api(`/api/posts/${id}`);
  view.innerHTML = `<div class="card"><h2>Possible matches</h2>
    <div class="muted">Searching ${post.post_type === "lost" ? "found" : "lost"} pet posts in every participating group.</div></div>
    ${postCard(post, { showFind: false })}
    <div id="results" class="card empty"><span class="spinner"></span> Comparing photos and details...</div>`;
  const matches = await api(`/api/posts/${id}/matches`);
  const box = document.getElementById("results");
  if (!matches.length) {
    box.textContent = "No possible matches yet. You'll get a notification if one is posted.";
    return;
  }
  box.outerHTML = matches.map(matchCard).join("");
}

async function showNotifications() {
  const items = await api("/api/notifications");
  view.innerHTML = `<div class="card"><h2>Notifications</h2>
    <div class="muted">Sent automatically when a new post strongly matches an existing one.</div></div>` +
    (items.length ? items.map((n) => `<article class="card">
      <div><strong>${esc(n.poster)}</strong>, a new ${n.match ? esc(n.match.post_type) : ""} post is a
        <strong>${n.likelihood}%</strong> match for your ${esc(n.post_type)} pet.</div>
      <div class="muted">${esc(n.summary)}</div>
      ${n.match ? photoGrid(n.match.photos.slice(0, 2)) : ""}
      <div class="actions"><a class="btn primary" href="#matches/${n.post_id}">See matches</a></div>
    </article>`).join("") : `<div class="card empty">No notifications yet.</div>`);
}

async function showGroups() {
  const groups = await api("/api/groups");
  view.innerHTML = `<div class="card"><h2>Participating groups</h2>
    <p class="muted">Group admins choose whether their lost and found posts are searchable by anyone, without joining.
    Turning a group off removes its posts from every search straight away.</p>
    ${groups.map((g) => `<div class="group-row">
      <div><h3>${esc(g.name)}</h3><div class="muted">${esc(g.area)} &middot; ${g.members.toLocaleString()} members &middot; ${g.posts} pet posts</div></div>
      <label class="switch"><input type="checkbox" data-group="${esc(g.id)}" ${g.opted_in ? "checked" : ""}><span></span></label>
    </div>`).join("")}</div>
    <div class="card"><h3>Reset the demo</h3>
      <p class="muted">Puts every group and post back the way the demo started, removing posts added by visitors.</p>
      <button class="btn" id="reset-demo">Reset demo</button> <span id="reset-status" class="muted"></span></div>`;
  document.getElementById("reset-demo").addEventListener("click", async () => {
    const status = document.getElementById("reset-status");
    status.textContent = "Resetting...";
    try {
      await api("/api/reset", { method: "POST" });
      status.textContent = "Done.";
      showGroups();
    } catch (err) { status.textContent = err.message; }
  });
  view.querySelectorAll("input[data-group]").forEach((box) =>
    box.addEventListener("change", () => api(`/api/groups/${box.dataset.group}/opt-in`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ opted_in: box.checked }),
    })));
}

async function refreshBadge() {
  try {
    const n = (await api("/api/notifications")).length;
    const b = document.getElementById("notif-count");
    b.textContent = n;
    b.classList.toggle("hidden", !n);
  } catch { /* badge is decorative */ }
}

async function route() {
  const [name, arg] = (location.hash.slice(1) || "feed").split("/");
  document.querySelectorAll(".sidebar a").forEach((a) =>
    a.classList.toggle("active", a.dataset.view === name));
  try {
    if (name === "report") showReport();
    else if (name === "matches") await showMatches(arg);
    else if (name === "notifications") await showNotifications();
    else if (name === "groups") await showGroups();
    else await showFeed();
  } catch (err) {
    view.innerHTML = `<div class="card empty">Couldn't load this page: ${esc(err.message)}</div>`;
  }
  refreshBadge();
}

document.addEventListener("click", (e) => {
  const msg = e.target.closest("[data-message]");
  if (msg) {
    document.getElementById("modal-body").innerHTML = `<h3>Message ${esc(msg.dataset.poster)}</h3>
      <p class="muted">In the real feature this opens a Messenger chat with ${esc(msg.dataset.message)},
      with the matching post attached so they know which pet you mean.</p>`;
    modal.classList.remove("hidden");
  }
});
document.getElementById("modal-close").addEventListener("click", () => modal.classList.add("hidden"));
window.addEventListener("hashchange", route);
route();
