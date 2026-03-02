/* nanobot skills dashboard — card-based logic pipeline */
(function () {
    // -- Auth guard -----------------------------------------------------
    var token = localStorage.getItem("nanobot_token");
    if (!token) { window.location.href = "/login.html"; return; }

    var grid = document.getElementById("skills-grid");
    var searchInput = document.getElementById("search");
    var detailPanel = document.getElementById("detail-panel");
    var detailEmpty = document.getElementById("detail-empty");
    var detailName = document.getElementById("detail-name");
    var detailDesc = document.getElementById("detail-desc");
    var detailBadges = document.getElementById("detail-badges");
    var detailContent = document.getElementById("detail-content");
    var logoutBtn = document.getElementById("logout-btn");

    var allSkills = [];
    var activeCard = null;

    // Color themes for pipeline sections
    var COLORS = {
        blue:   { bg: "rgba(59,130,246,0.08)",  border: "rgba(59,130,246,0.2)",  icon: "#3b82f6", badge: "bg-blue-900/40 text-blue-300",   dot: "bg-blue-500"   },
        teal:   { bg: "rgba(20,184,166,0.08)",   border: "rgba(20,184,166,0.2)",  icon: "#14b8a6", badge: "bg-teal-900/40 text-teal-300",   dot: "bg-teal-500"   },
        purple: { bg: "rgba(139,92,246,0.08)",    border: "rgba(139,92,246,0.2)",  icon: "#8b5cf6", badge: "bg-purple-900/40 text-purple-300", dot: "bg-purple-500" },
        amber:  { bg: "rgba(245,158,11,0.08)",    border: "rgba(245,158,11,0.2)",  icon: "#f59e0b", badge: "bg-amber-900/40 text-amber-300",  dot: "bg-amber-500"  },
        rose:   { bg: "rgba(244,63,94,0.08)",     border: "rgba(244,63,94,0.2)",   icon: "#f43f5e", badge: "bg-rose-900/40 text-rose-300",    dot: "bg-rose-500"   }
    };
    var STEP_ICONS = { action: "fa-solid fa-gear", decision: "fa-solid fa-code-branch", output: "fa-solid fa-flag-checkered" };

    // -- Helpers --------------------------------------------------------

    function authHeaders(extra) {
        var h = { "Authorization": "Bearer " + token };
        if (extra) { for (var k in extra) { h[k] = extra[k]; } }
        return h;
    }

    function handleUnauthorized(resp) {
        if (resp.status === 401) {
            localStorage.removeItem("nanobot_token");
            localStorage.removeItem("nanobot_user");
            window.location.href = "/login.html";
            return true;
        }
        return false;
    }

    function esc(s) { var el = document.createElement("span"); el.textContent = s; return el.innerHTML; }

    function badge(text, color) {
        return '<span class="inline-block text-xs font-medium px-2 py-0.5 rounded-full ' + color + '">' + text + '</span>';
    }

    function tryParseJSON(text) {
        if (!text) return null;
        // Strip markdown fences if LLM wrapped them
        var cleaned = text.replace(/^```json?\s*\n?/i, "").replace(/\n?```\s*$/i, "").trim();
        try { return JSON.parse(cleaned); }
        catch (e) { return null; }
    }

    // -- Render skill card list -----------------------------------------

    function renderCards(skills) {
        grid.innerHTML = "";
        skills.forEach(function (s) {
            var card = document.createElement("div");
            card.className = "skill-card cursor-pointer border border-gray-700 rounded-lg p-4";
            card.dataset.name = s.name;

            var badges = "";
            badges += badge(s.source, s.source === "builtin" ? "bg-purple-900/40 text-purple-300" : "bg-green-900/40 text-green-300");
            if (s.always_on) badges += " " + badge("always-on", "bg-yellow-900/40 text-yellow-300");
            if (!s.available) badges += " " + badge("unavailable", "bg-red-900/40 text-red-300");
            if (s.has_logic) badges += " " + badge("pipeline", "bg-blue-900/40 text-blue-300");

            card.innerHTML =
                '<div class="font-semibold text-gray-100">' + esc(s.name) + '</div>' +
                '<div class="text-sm text-gray-400 mt-1 line-clamp-2">' + esc(s.description || "") + '</div>' +
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

    // -- Load skill detail ----------------------------------------------

    async function loadDetail(name) {
        detailPanel.classList.remove("hidden");
        detailPanel.classList.add("flex");
        detailEmpty.classList.add("hidden");
        detailContent.innerHTML = '<div class="text-gray-500 p-8">Loading...</div>';

        try {
            var resp = await fetch("/api/skills/" + encodeURIComponent(name), { headers: authHeaders() });
            if (handleUnauthorized(resp)) return;
            if (!resp.ok) { detailContent.innerHTML = '<div class="text-red-400 p-8">Failed to load skill.</div>'; return; }
            var data = await resp.json();

            detailName.textContent = data.name;
            detailDesc.textContent = data.description || "";

            var badges = "";
            badges += badge(data.source, data.source === "builtin" ? "bg-purple-900/40 text-purple-300" : "bg-green-900/40 text-green-300");
            if (data.always_on) badges += " " + badge("always-on", "bg-yellow-900/40 text-yellow-300");
            if (!data.available) badges += " " + badge("unavailable", "bg-red-900/40 text-red-300");
            if (data.has_python) badges += " " + badge("python", "bg-emerald-900/40 text-emerald-300");
            else badges += " " + badge("markdown-only", "bg-gray-700 text-gray-400");
            detailBadges.innerHTML = badges;

            var pipeline = tryParseJSON(data.logic);

            var html = _headerBar(!!data.logic);

            if (pipeline && pipeline.entry_point) {
                html += renderPipeline(pipeline);
            } else if (data.logic) {
                // Legacy or unparseable — show raw text in a card
                html += _card("blue", "fa-solid fa-file-lines", "Pipeline (raw)",
                    '<pre class="text-sm text-gray-300 whitespace-pre-wrap">' + esc(data.logic) + '</pre>');
            } else {
                html += _emptyState();
            }

            detailContent.innerHTML = html;
            _bindBtn(name);
        } catch (err) {
            detailContent.innerHTML = '<div class="text-red-400 p-8">Error: ' + esc(err.message) + '</div>';
        }
    }

    // -- Render structured pipeline as cards + timeline ------------------

    function renderPipeline(p) {
        var h = "";

        // Entry point card
        var icon = (p.entry_point.icon || "fa-solid fa-bolt").replace(/"/g, "");
        h += _card("blue", icon, "Entry Point",
            '<p class="text-gray-300">' + esc(p.entry_point.trigger || "") + '</p>');

        // Pipeline timeline
        if (p.steps && p.steps.length) {
            h += '<div class="pipe-card" style="background:' + COLORS.teal.bg + ';border:1px solid ' + COLORS.teal.border + ';border-radius:1rem;padding:1.5rem;margin-bottom:1rem;">';
            h += '<div class="flex items-center mb-4"><i class="fa-solid fa-diagram-project text-xl mr-3" style="color:' + COLORS.teal.icon + '"></i>';
            h += '<h3 class="text-lg font-bold text-gray-100">Pipeline</h3></div>';
            h += '<div class="relative ml-4">';
            // Vertical line
            h += '<div class="absolute left-3.5 top-0 bottom-0 w-0.5 bg-teal-800"></div>';
            for (var i = 0; i < p.steps.length; i++) {
                var s = p.steps[i];
                var stepIcon = STEP_ICONS[s.type] || STEP_ICONS.action;
                var num = i + 1;
                h += '<div class="flex items-start mb-5 last:mb-0 relative">';
                h += '<div class="flex-shrink-0 w-7 h-7 rounded-full ' + COLORS.teal.dot + ' flex items-center justify-center text-white text-xs font-bold z-10">' + num + '</div>';
                h += '<div class="ml-4">';
                h += '<div class="flex items-center gap-2">';
                h += '<i class="' + stepIcon + ' text-sm" style="color:' + COLORS.teal.icon + '"></i>';
                h += '<span class="font-semibold text-gray-100">' + esc(s.title || "") + '</span>';
                if (s.type === "decision") h += ' <span class="text-xs px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-300">decision</span>';
                if (s.type === "output") h += ' <span class="text-xs px-1.5 py-0.5 rounded bg-emerald-900/40 text-emerald-300">output</span>';
                h += '</div>';
                h += '<p class="text-sm text-gray-400 mt-0.5">' + esc(s.description || "") + '</p>';
                h += '</div></div>';
            }
            h += '</div></div>';
        }

        // Dependencies card
        if (p.dependencies && p.dependencies.length) {
            var depHtml = '<div class="grid grid-cols-1 sm:grid-cols-2 gap-2">';
            for (var d = 0; d < p.dependencies.length; d++) {
                var dep = p.dependencies[d];
                depHtml += '<div class="rounded-lg p-3" style="background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.15)">';
                depHtml += '<div class="font-semibold text-sm text-gray-200">' + esc(dep.name || "") + '</div>';
                depHtml += '<div class="text-xs text-gray-400 mt-0.5">' + esc(dep.description || "") + '</div>';
                depHtml += '</div>';
            }
            depHtml += '</div>';
            h += _card("purple", "fa-solid fa-puzzle-piece", "Dependencies", depHtml);
        }

        // Class design card (for no-code skills)
        if (p.class_design && p.class_design.class_name) {
            var clsHtml = '<div class="mb-2"><span class="font-mono text-amber-300 text-sm">class ' + esc(p.class_design.class_name) + '</span></div>';
            if (p.class_design.methods && p.class_design.methods.length) {
                clsHtml += '<div class="space-y-1">';
                for (var m = 0; m < p.class_design.methods.length; m++) {
                    var mt = p.class_design.methods[m];
                    clsHtml += '<div class="flex items-start gap-2 rounded-lg p-2" style="background:rgba(245,158,11,0.08)">';
                    clsHtml += '<i class="fa-solid fa-terminal text-xs mt-1" style="color:#f59e0b"></i>';
                    clsHtml += '<div><span class="font-mono text-sm text-gray-200">' + esc(mt.name || "") + '()</span>';
                    clsHtml += '<span class="text-xs text-gray-400 ml-2">' + esc(mt.description || "") + '</span></div>';
                    clsHtml += '</div>';
                }
                clsHtml += '</div>';
            }
            h += _card("amber", "fa-solid fa-code", "Reconstructed Class", clsHtml);
        }

        return h;
    }

    // -- Card builder helper (reference page style) ---------------------

    function _card(color, icon, title, bodyHtml) {
        var c = COLORS[color] || COLORS.blue;
        return '<div class="pipe-card" style="background:' + c.bg + ';border:1px solid ' + c.border + ';border-radius:1rem;padding:1.5rem;margin-bottom:1rem;position:relative;overflow:hidden;">'
            + '<div class="flex items-center mb-3">'
            + '<i class="' + icon + ' text-xl mr-3" style="color:' + c.icon + '"></i>'
            + '<h3 class="text-lg font-bold text-gray-100">' + title + '</h3>'
            + '</div>'
            + bodyHtml
            + '</div>';
    }

    // -- Header bar with generate/regenerate button ---------------------

    function _headerBar(hasLogic) {
        var h = '<div class="flex items-center justify-between mb-5 pb-4 border-b border-gray-700">';
        h += '<h2 class="text-lg font-bold text-gray-100">Logic Pipeline</h2>';
        h += '<button id="gen-logic-btn" class="flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-md transition ';
        if (hasLogic) {
            h += 'bg-gray-700 hover:bg-gray-600 text-gray-300 hover:text-white" title="Regenerate pipeline">';
            h += '<i class="fa-solid fa-rotate"></i> Regenerate';
        } else {
            h += 'bg-blue-600 hover:bg-blue-500 text-white" title="Generate pipeline">';
            h += '<i class="fa-solid fa-wand-magic-sparkles"></i> Generate Pipeline';
        }
        h += '</button></div>';
        return h;
    }

    function _emptyState() {
        return '<div class="text-center py-16">'
            + '<div class="mb-4"><i class="fa-solid fa-diagram-project text-5xl text-gray-700"></i></div>'
            + '<p class="text-gray-500">No logic pipeline generated yet.</p>'
            + '<p class="text-gray-600 text-sm mt-1">Click the button above to generate.</p>'
            + '</div>';
    }

    function _bindBtn(name) {
        var btn = document.getElementById("gen-logic-btn");
        if (btn) btn.addEventListener("click", function () { generateLogic(name); });
    }

    // -- Generate / refresh logic pipeline ------------------------------

    async function generateLogic(name) {
        detailContent.innerHTML =
            '<div class="flex flex-col items-center justify-center py-20">'
            + '<div class="typing-dots text-3xl text-blue-400 mb-4"><span>.</span><span>.</span><span>.</span></div>'
            + '<p class="text-gray-400 font-medium">Generating logic pipeline...</p>'
            + '<p class="text-gray-600 text-sm mt-1">The agent is analyzing this skill</p>'
            + '</div>';

        try {
            var resp = await fetch("/api/skills/" + encodeURIComponent(name) + "/generate-logic", {
                method: "POST", headers: authHeaders(),
            });
            if (handleUnauthorized(resp)) return;
            if (!resp.ok) throw new Error("Generation failed");

            for (var i = 0; i < allSkills.length; i++) {
                if (allSkills[i].name === name) { allSkills[i].has_logic = true; break; }
            }
            await loadDetail(name);
        } catch (err) {
            detailContent.innerHTML = _headerBar(false)
                + '<div class="text-center py-12"><p class="text-red-400 mb-4">Pipeline generation failed: '
                + esc(err.message) + '</p></div>';
            _bindBtn(name);
        }
    }

    // -- Search / filter ------------------------------------------------

    searchInput.addEventListener("input", function () {
        var q = this.value.toLowerCase();
        var filtered = allSkills.filter(function (s) {
            return s.name.toLowerCase().includes(q) || (s.description || "").toLowerCase().includes(q);
        });
        renderCards(filtered);
    });

    // -- Logout ---------------------------------------------------------

    if (logoutBtn) {
        logoutBtn.addEventListener("click", function () {
            localStorage.removeItem("nanobot_token");
            localStorage.removeItem("nanobot_user");
            localStorage.removeItem("nanobot_session");
            window.location.href = "/login.html";
        });
    }

    // -- Init -----------------------------------------------------------

    async function init() {
        try {
            var resp = await fetch("/api/skills", { headers: authHeaders() });
            if (handleUnauthorized(resp)) return;
            var data = await resp.json();
            allSkills = data.skills || [];
            renderCards(allSkills);
        } catch (err) {
            grid.innerHTML = '<div class="text-red-400 p-4">Failed to load skills: ' + esc(err.message) + '</div>';
        }
    }

    init();
})();
