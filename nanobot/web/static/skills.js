/* nanobot skills dashboard — server-rendered pipeline view */
(function () {
    var token = localStorage.getItem("nanobot_token");
    if (!token) { window.location.href = "/login.html"; return; }

    var grid = document.getElementById("skills-grid");
    var searchInput = document.getElementById("search");
    var detailName = document.getElementById("detail-name");
    var detailDesc = document.getElementById("detail-desc");
    var detailBadges = document.getElementById("detail-badges");
    var detailContent = document.getElementById("detail-content");
    var logoutBtn = document.getElementById("logout-btn");

    var allSkills = [];
    var activeCard = null;

    /* ---- Drag-to-resize ---- */
    (function () {
        var handle = document.getElementById("drag-handle");
        var left = document.getElementById("left-panel");
        var container = document.getElementById("split-container");
        var dragging = false;
        handle.addEventListener("mousedown", function (e) {
            e.preventDefault(); dragging = true;
            handle.classList.add("dragging");
            document.body.classList.add("col-resizing");
        });
        document.addEventListener("mousemove", function (e) {
            if (!dragging) return;
            var rect = container.getBoundingClientRect();
            var pct = ((e.clientX - rect.left) / rect.width) * 100;
            left.style.width = Math.min(70, Math.max(15, pct)) + "%";
        });
        document.addEventListener("mouseup", function () {
            if (!dragging) return; dragging = false;
            handle.classList.remove("dragging");
            document.body.classList.remove("col-resizing");
        });
    })();

    /* ---- Helpers ---- */
    var B = {
        builtin:  "background:rgba(139,92,246,0.18);color:#c4b5fd",
        workspace:"background:rgba(34,197,94,0.18);color:#86efac",
        always:   "background:rgba(234,179,8,0.18);color:#fde047",
        unavail:  "background:rgba(239,68,68,0.18);color:#fca5a5",
        pipeline: "background:rgba(59,130,246,0.18);color:#93c5fd",
        python:   "background:rgba(16,185,129,0.18);color:#6ee7b7",
        mdonly:   "background:rgba(107,114,128,0.25);color:#9ca3af"
    };

    function authHeaders(extra) {
        var h = { "Authorization": "Bearer " + token };
        if (extra) for (var k in extra) h[k] = extra[k];
        return h;
    }
    function handleUnauthorized(r) {
        if (r.status === 401) {
            localStorage.removeItem("nanobot_token");
            localStorage.removeItem("nanobot_user");
            window.location.href = "/login.html"; return true;
        }
        return false;
    }
    function esc(s) { var e = document.createElement("span"); e.textContent = s; return e.innerHTML; }
    function stBadge(text, style) {
        return '<span style="display:inline-block;font-size:0.7rem;font-weight:500;padding:2px 8px;border-radius:9999px;' + style + '">' + text + '</span>';
    }

    /* ---- Skill card list ---- */
    function renderCards(skills) {
        grid.innerHTML = "";
        skills.forEach(function (s) {
            var card = document.createElement("div");
            card.className = "skill-card cursor-pointer border border-gray-700 rounded-lg p-4";
            var badges = stBadge(s.source, s.source === "builtin" ? B.builtin : B.workspace);
            if (s.always_on) badges += " " + stBadge("always-on", B.always);
            if (!s.available) badges += " " + stBadge("unavailable", B.unavail);
            if (s.has_logic) badges += " " + stBadge("pipeline", B.pipeline);
            card.innerHTML =
                '<div class="font-semibold text-gray-100">' + esc(s.name) + '</div>' +
                '<div class="text-sm text-gray-400 mt-1" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">' + esc(s.description || "") + '</div>' +
                '<div class="flex gap-1 mt-2 flex-wrap">' + badges + '</div>';
            card.addEventListener("click", function () {
                if (activeCard) activeCard.classList.remove("active");
                card.classList.add("active");
                activeCard = card;
                loadDetail(s.name);
            });
            grid.appendChild(card);
        });
    }

    /* ---- Load skill detail — server renders HTML ---- */
    async function loadDetail(name) {
        detailContent.innerHTML = '<div class="text-gray-500 p-8">Loading...</div>';
        try {
            var resp = await fetch("/api/skills/" + encodeURIComponent(name), { headers: authHeaders() });
            if (handleUnauthorized(resp)) return;
            if (!resp.ok) { detailContent.innerHTML = '<div class="text-red-400 p-8">Failed to load.</div>'; return; }
            var data = await resp.json();

            detailName.textContent = data.name;
            detailDesc.textContent = data.description || "";
            var badges = stBadge(data.source, data.source === "builtin" ? B.builtin : B.workspace);
            if (data.always_on) badges += " " + stBadge("always-on", B.always);
            if (!data.available) badges += " " + stBadge("unavailable", B.unavail);
            badges += " " + stBadge(data.has_python ? "python" : "markdown-only", data.has_python ? B.python : B.mdonly);
            detailBadges.innerHTML = badges;

            // Header bar with generate/regenerate button
            var html = headerBar(data.has_logic);

            if (data.logic_html) {
                // Server-rendered pipeline HTML — just inject it
                html += data.logic_html;
            } else {
                html += emptyState();
            }

            detailContent.innerHTML = html;
            bindBtn(name);
        } catch (err) {
            detailContent.innerHTML = '<div class="text-red-400 p-8">Error: ' + esc(err.message) + '</div>';
        }
    }

    function headerBar(hasLogic) {
        var h = '<div class="flex items-center justify-between mb-5 pb-4 border-b border-gray-700">';
        h += '<h2 class="text-lg font-bold text-gray-100">Logic Pipeline</h2>';
        h += '<button id="gen-logic-btn" class="flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-md transition ';
        if (hasLogic) {
            h += 'bg-gray-700 text-gray-300 hover:text-white" style="border:1px solid rgba(255,255,255,0.1)" title="Regenerate">';
            h += '<i class="fa-solid fa-rotate"></i> Regenerate';
        } else {
            h += 'text-white" style="background:#3b82f6" title="Generate">';
            h += '<i class="fa-solid fa-wand-magic-sparkles"></i> Generate Pipeline';
        }
        h += '</button></div>';
        return h;
    }

    function emptyState() {
        return '<div class="text-center py-16">'
            + '<div class="mb-4"><i class="fa-solid fa-diagram-project text-5xl text-gray-700"></i></div>'
            + '<p class="text-gray-500">No logic pipeline generated yet.</p>'
            + '<p class="text-gray-600 text-sm mt-1">Click the button above to generate.</p></div>';
    }

    function bindBtn(name) {
        var btn = document.getElementById("gen-logic-btn");
        if (btn) btn.addEventListener("click", function () { generateLogic(name); });
    }

    /* ---- Generate pipeline ---- */
    async function generateLogic(name) {
        detailContent.innerHTML = '<div class="flex flex-col items-center justify-center py-20">'
            + '<div class="typing-dots text-3xl text-blue-400 mb-4"><span>.</span><span>.</span><span>.</span></div>'
            + '<p class="text-gray-400 font-medium">Agent is analyzing this skill...</p>'
            + '<p class="text-gray-600 text-sm mt-1">Extracting logic pipeline via LLM</p></div>';
        try {
            var resp = await fetch("/api/skills/" + encodeURIComponent(name) + "/generate-logic", {
                method: "POST", headers: authHeaders() });
            if (handleUnauthorized(resp)) return;
            if (!resp.ok) {
                var err = await resp.json().catch(function () { return {}; });
                throw new Error(err.detail || "Generation failed");
            }
            for (var i = 0; i < allSkills.length; i++) {
                if (allSkills[i].name === name) { allSkills[i].has_logic = true; break; }
            }
            await loadDetail(name);
        } catch (err) {
            detailContent.innerHTML = headerBar(false)
                + '<div class="text-center py-12"><p class="text-red-400">' + esc(err.message) + '</p></div>';
            bindBtn(name);
        }
    }

    /* ---- Search ---- */
    searchInput.addEventListener("input", function () {
        var q = this.value.toLowerCase();
        renderCards(allSkills.filter(function (s) {
            return s.name.toLowerCase().includes(q) || (s.description || "").toLowerCase().includes(q);
        }));
    });

    /* ---- Logout ---- */
    if (logoutBtn) logoutBtn.addEventListener("click", function () {
        localStorage.removeItem("nanobot_token");
        localStorage.removeItem("nanobot_user");
        localStorage.removeItem("nanobot_session");
        window.location.href = "/login.html";
    });

    /* ---- Init ---- */
    (async function () {
        try {
            var resp = await fetch("/api/skills", { headers: authHeaders() });
            if (handleUnauthorized(resp)) return;
            var data = await resp.json();
            allSkills = data.skills || [];
            renderCards(allSkills);
        } catch (err) {
            grid.innerHTML = '<div class="text-red-400 p-4">Failed to load skills: ' + esc(err.message) + '</div>';
        }
    })();
})();
