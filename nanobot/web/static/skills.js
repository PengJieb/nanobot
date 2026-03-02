/* nanobot skills dashboard — card-based logic pipeline with decision branches */
(function () {
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

    /* Badge styles using inline rgba — avoids Tailwind JIT issues with /40 */
    var B = {
        builtin:  "background:rgba(139,92,246,0.18);color:#c4b5fd",
        workspace:"background:rgba(34,197,94,0.18);color:#86efac",
        always:   "background:rgba(234,179,8,0.18);color:#fde047",
        unavail:  "background:rgba(239,68,68,0.18);color:#fca5a5",
        pipeline: "background:rgba(59,130,246,0.18);color:#93c5fd",
        python:   "background:rgba(16,185,129,0.18);color:#6ee7b7",
        mdonly:   "background:rgba(107,114,128,0.25);color:#9ca3af",
        decision: "background:rgba(245,158,11,0.18);color:#fcd34d",
        output:   "background:rgba(16,185,129,0.18);color:#6ee7b7"
    };

    var STEP_ICONS = { action: "fa-solid fa-gear", decision: "fa-solid fa-code-branch", output: "fa-solid fa-flag-checkered" };

    function authHeaders(extra) {
        var h = { "Authorization": "Bearer " + token };
        if (extra) for (var k in extra) h[k] = extra[k];
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
    function esc(s) { var e = document.createElement("span"); e.textContent = s; return e.innerHTML; }
    function stBadge(text, style) {
        return '<span style="display:inline-block;font-size:0.7rem;font-weight:500;padding:2px 8px;border-radius:9999px;' + style + '">' + text + '</span>';
    }
    function tryParseJSON(text) {
        if (!text) return null;
        var c = text.replace(/^```json?\s*\n?/i, "").replace(/\n?```\s*$/i, "").trim();
        try { return JSON.parse(c); } catch (e) { return null; }
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

    /* ---- Load skill detail ---- */
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
            var badges = stBadge(data.source, data.source === "builtin" ? B.builtin : B.workspace);
            if (data.always_on) badges += " " + stBadge("always-on", B.always);
            if (!data.available) badges += " " + stBadge("unavailable", B.unavail);
            badges += " " + stBadge(data.has_python ? "python" : "markdown-only", data.has_python ? B.python : B.mdonly);
            detailBadges.innerHTML = badges;

            var pipeline = tryParseJSON(data.logic);
            var html = headerBar(!!data.logic);
            if (pipeline && pipeline.entry_point) {
                html += renderPipeline(pipeline);
            } else if (data.logic) {
                html += card("blue", "fa-solid fa-file-lines", "Pipeline (raw)",
                    '<pre class="text-sm text-gray-300 whitespace-pre-wrap">' + esc(data.logic) + '</pre>');
            } else {
                html += emptyState();
            }
            detailContent.innerHTML = html;
            bindBtn(name);
        } catch (err) {
            detailContent.innerHTML = '<div class="text-red-400 p-8">Error: ' + esc(err.message) + '</div>';
        }
    }

    /* ---- Render pipeline with decision branches ---- */
    function renderPipeline(p) {
        var h = "";
        var icon = (p.entry_point.icon || "fa-solid fa-bolt").replace(/"/g, "");
        h += card("blue", icon, "Entry Point", '<p class="text-gray-300">' + esc(p.entry_point.trigger || "") + '</p>');

        if (p.steps && p.steps.length) {
            h += '<div class="pipe-card" style="background:rgba(20,184,166,0.08);border:1px solid rgba(20,184,166,0.2);border-radius:1rem;padding:1.5rem;margin-bottom:1rem;">';
            h += '<div class="flex items-center mb-4"><i class="fa-solid fa-diagram-project text-xl mr-3" style="color:#14b8a6"></i>';
            h += '<h3 class="text-lg font-bold text-gray-100">Pipeline</h3></div>';
            h += renderSteps(p.steps, 0);
            h += '</div>';
        }

        if (p.dependencies && p.dependencies.length) {
            var dh = '<div class="grid grid-cols-1 gap-2" style="grid-template-columns:repeat(auto-fill,minmax(200px,1fr))">';
            for (var d = 0; d < p.dependencies.length; d++) {
                var dep = p.dependencies[d];
                dh += '<div style="background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.15);border-radius:0.5rem;padding:0.75rem">';
                dh += '<div class="font-semibold text-sm text-gray-200">' + esc(dep.name || "") + '</div>';
                dh += '<div class="text-xs text-gray-400 mt-0.5">' + esc(dep.description || "") + '</div></div>';
            }
            dh += '</div>';
            h += card("purple", "fa-solid fa-puzzle-piece", "Dependencies", dh);
        }

        if (p.class_design && p.class_design.class_name) {
            var ch = '<div class="mb-2"><span class="font-mono" style="color:#fcd34d;font-size:0.875rem">class ' + esc(p.class_design.class_name) + '</span></div>';
            if (p.class_design.methods && p.class_design.methods.length) {
                ch += '<div class="space-y-1">';
                for (var m = 0; m < p.class_design.methods.length; m++) {
                    var mt = p.class_design.methods[m];
                    ch += '<div class="flex items-start gap-2 rounded-lg p-2" style="background:rgba(245,158,11,0.08)">';
                    ch += '<i class="fa-solid fa-terminal text-xs mt-1" style="color:#f59e0b"></i>';
                    ch += '<div><span class="font-mono text-sm text-gray-200">' + esc(mt.name || "") + '()</span>';
                    ch += ' <span class="text-xs text-gray-400">' + esc(mt.description || "") + '</span></div></div>';
                }
                ch += '</div>';
            }
            h += card("amber", "fa-solid fa-code", "Reconstructed Class", ch);
        }
        return h;
    }

    /** Render steps recursively — handles decision branches */
    function renderSteps(steps, depth) {
        var ml = depth > 0 ? "margin-left:1.5rem;" : "margin-left:1rem;";
        var dotColor = depth === 0 ? "#14b8a6" : (depth === 1 ? "#f59e0b" : "#f43f5e");
        var lineColor = depth === 0 ? "rgba(20,184,166,0.3)" : "rgba(245,158,11,0.3)";
        var h = '<div class="relative" style="' + ml + '">';
        h += '<div class="absolute top-0 bottom-0 w-0.5" style="left:13px;background:' + lineColor + '"></div>';

        for (var i = 0; i < steps.length; i++) {
            var s = steps[i];
            var num = i + 1;
            var stepIcon = STEP_ICONS[s.type] || STEP_ICONS.action;
            h += '<div class="flex items-start mb-4 relative">';
            h += '<div class="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold z-10" style="background:' + dotColor + '">' + num + '</div>';
            h += '<div class="ml-4 flex-1">';
            h += '<div class="flex items-center gap-2 flex-wrap">';
            h += '<i class="' + stepIcon + ' text-sm" style="color:' + dotColor + '"></i>';
            h += '<span class="font-semibold text-gray-100">' + esc(s.title || "") + '</span>';
            if (s.type === "decision") h += stBadge("decision", B.decision);
            if (s.type === "output") h += stBadge("output", B.output);
            h += '</div>';
            h += '<p class="text-sm text-gray-400 mt-0.5">' + esc(s.description || "") + '</p>';

            /* Decision branches */
            if (s.type === "decision" && s.branches) {
                h += '<div class="mt-3 space-y-3">';
                var branchKeys = Object.keys(s.branches);
                for (var b = 0; b < branchKeys.length; b++) {
                    var bk = branchKeys[b];
                    var branch = s.branches[bk];
                    var bColor = bk === "yes" ? "#14b8a6" : "#f43f5e";
                    var bBg = bk === "yes" ? "rgba(20,184,166,0.08)" : "rgba(244,63,94,0.08)";
                    var bBorder = bk === "yes" ? "rgba(20,184,166,0.2)" : "rgba(244,63,94,0.2)";
                    var bIcon = bk === "yes" ? "fa-solid fa-check" : "fa-solid fa-xmark";

                    h += '<div style="background:' + bBg + ';border:1px solid ' + bBorder + ';border-radius:0.75rem;padding:0.75rem 1rem">';
                    h += '<div class="flex items-center gap-2 mb-2">';
                    h += '<i class="' + bIcon + '" style="color:' + bColor + '"></i>';
                    h += '<span class="font-semibold text-sm" style="color:' + bColor + '">' + esc(bk.toUpperCase()) + '</span>';
                    h += '<span class="text-xs text-gray-400">' + esc(branch.label || "") + '</span>';
                    h += '</div>';
                    if (branch.steps && branch.steps.length) {
                        h += renderSteps(branch.steps, depth + 1);
                    }
                    h += '</div>';
                }
                h += '</div>';
            }
            h += '</div></div>';
        }
        h += '</div>';
        return h;
    }

    /* ---- Card helper ---- */
    var CARD_COLORS = {
        blue:   { bg: "rgba(59,130,246,0.08)",  border: "rgba(59,130,246,0.2)",  icon: "#3b82f6" },
        teal:   { bg: "rgba(20,184,166,0.08)",   border: "rgba(20,184,166,0.2)",  icon: "#14b8a6" },
        purple: { bg: "rgba(139,92,246,0.08)",    border: "rgba(139,92,246,0.2)",  icon: "#8b5cf6" },
        amber:  { bg: "rgba(245,158,11,0.08)",    border: "rgba(245,158,11,0.2)",  icon: "#f59e0b" }
    };

    function card(color, icon, title, body) {
        var c = CARD_COLORS[color] || CARD_COLORS.blue;
        return '<div class="pipe-card" style="background:' + c.bg + ';border:1px solid ' + c.border + ';border-radius:1rem;padding:1.5rem;margin-bottom:1rem">'
            + '<div class="flex items-center mb-3"><i class="' + icon + ' text-xl mr-3" style="color:' + c.icon + '"></i>'
            + '<h3 class="text-lg font-bold text-gray-100">' + title + '</h3></div>' + body + '</div>';
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
            + '<p class="text-gray-400 font-medium">Generating logic pipeline...</p></div>';
        try {
            var resp = await fetch("/api/skills/" + encodeURIComponent(name) + "/generate-logic", {
                method: "POST", headers: authHeaders() });
            if (handleUnauthorized(resp)) return;
            if (!resp.ok) throw new Error("Generation failed");
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
