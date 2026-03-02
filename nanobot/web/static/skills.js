/* nanobot skills dashboard — logic pipeline view */
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
    // Track which skill is currently shown so refresh works correctly
    var currentSkillName = null;

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

    function badge(text, color) {
        return '<span class="inline-block text-xs font-medium px-2 py-0.5 rounded-full ' + color + '">' + text + '</span>';
    }

    function renderMarkdown(text) {
        try { return marked.parse(text); }
        catch (e) { return text.replace(/</g, "&lt;").replace(/\n/g, "<br>"); }
    }

    // -- Render skill list ----------------------------------------------

    function renderCards(skills) {
        grid.innerHTML = "";
        skills.forEach(function (s) {
            var card = document.createElement("div");
            card.className = "skill-card cursor-pointer border border-gray-700 rounded-lg p-4";
            card.dataset.name = s.name;

            var badges = "";
            badges += badge(s.source, s.source === "builtin" ? "bg-purple-800 text-purple-200" : "bg-green-800 text-green-200");
            if (s.always_on) badges += " " + badge("always-on", "bg-yellow-800 text-yellow-200");
            if (!s.available) badges += " " + badge("unavailable", "bg-red-900 text-red-300");
            if (s.has_logic) badges += " " + badge("pipeline", "bg-blue-800 text-blue-200");

            card.innerHTML =
                '<div class="font-semibold text-gray-100">' + s.name + '</div>' +
                '<div class="text-sm text-gray-400 mt-1 line-clamp-2">' + (s.description || "") + '</div>' +
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

    // -- Load skill detail (logic pipeline view) ------------------------

    async function loadDetail(name) {
        currentSkillName = name;
        detailPanel.classList.remove("hidden");
        detailPanel.classList.add("flex");
        detailEmpty.classList.add("hidden");
        detailContent.innerHTML = '<div class="text-gray-500">Loading...</div>';

        try {
            var resp = await fetch("/api/skills/" + encodeURIComponent(name), {
                headers: authHeaders(),
            });
            if (handleUnauthorized(resp)) return;
            if (!resp.ok) {
                detailContent.innerHTML = '<div class="text-red-400">Failed to load skill.</div>';
                return;
            }
            var data = await resp.json();

            detailName.textContent = data.name;
            detailDesc.textContent = data.description || "";

            // Badges
            var badges = "";
            badges += badge(data.source, data.source === "builtin" ? "bg-purple-800 text-purple-200" : "bg-green-800 text-green-200");
            if (data.always_on) badges += " " + badge("always-on", "bg-yellow-800 text-yellow-200");
            if (!data.available) badges += " " + badge("unavailable", "bg-red-900 text-red-300");
            if (data.has_python) badges += " " + badge("python", "bg-emerald-800 text-emerald-200");
            else badges += " " + badge("markdown-only", "bg-gray-600 text-gray-300");
            detailBadges.innerHTML = badges;

            // Build the detail view
            var html = "";

            if (data.logic) {
                // Show cached logic pipeline + refresh button
                html += _pipelineHeader(true);
                html += '<div class="pipeline-content">' + renderMarkdown(data.logic) + '</div>';
            } else {
                // No pipeline yet — show generate button
                html += _pipelineHeader(false);
                html += '<div class="text-center py-12">';
                html += '<p class="text-gray-500 mb-4">No logic pipeline generated yet.</p>';
                html += '<button id="gen-logic-btn" class="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg font-medium transition">';
                html += 'Generate Pipeline';
                html += '</button>';
                html += '</div>';
            }

            detailContent.innerHTML = html;
            _bindButtons(name);
        } catch (err) {
            detailContent.innerHTML = '<div class="text-red-400">Error: ' + err.message + '</div>';
        }
    }

    function _pipelineHeader(hasLogic) {
        var h = '<div class="flex items-center justify-between mb-4">';
        h += '<h2 class="text-lg font-bold">Logic Pipeline</h2>';
        if (hasLogic) {
            h += '<button id="refresh-logic-btn" class="flex items-center gap-1.5 text-sm text-gray-400 hover:text-blue-400 transition" title="Regenerate pipeline">';
            h += '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">';
            h += '<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>';
            h += '</svg>';
            h += 'Refresh';
            h += '</button>';
        }
        h += '</div>';
        return h;
    }

    function _bindButtons(name) {
        var genBtn = document.getElementById("gen-logic-btn");
        if (genBtn) {
            genBtn.addEventListener("click", function () { generateLogic(name); });
        }
        var refreshBtn = document.getElementById("refresh-logic-btn");
        if (refreshBtn) {
            refreshBtn.addEventListener("click", function () { generateLogic(name); });
        }
    }

    // -- Generate / refresh logic pipeline ------------------------------

    async function generateLogic(name) {
        // Replace content with generating state
        detailContent.innerHTML =
            '<div class="flex flex-col items-center justify-center py-16">' +
            '<div class="typing-dots text-2xl text-blue-400 mb-4"><span>.</span><span>.</span><span>.</span></div>' +
            '<p class="text-gray-400">Generating logic pipeline via agent...</p>' +
            '</div>';

        try {
            var resp = await fetch("/api/skills/" + encodeURIComponent(name) + "/generate-logic", {
                method: "POST",
                headers: authHeaders(),
            });
            if (handleUnauthorized(resp)) return;
            if (!resp.ok) throw new Error("Generation failed");

            // Update the has_logic badge in the card list
            for (var i = 0; i < allSkills.length; i++) {
                if (allSkills[i].name === name) { allSkills[i].has_logic = true; break; }
            }

            // Reload the detail to show fresh pipeline
            await loadDetail(name);
        } catch (err) {
            detailContent.innerHTML =
                '<div class="text-center py-12">' +
                '<p class="text-red-400 mb-4">Pipeline generation failed: ' + err.message + '</p>' +
                '<button id="gen-logic-btn" class="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg font-medium transition">' +
                'Retry' +
                '</button>' +
                '</div>';
            _bindButtons(name);
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
            grid.innerHTML = '<div class="text-red-400 p-4">Failed to load skills: ' + err.message + '</div>';
        }
    }

    init();
})();
