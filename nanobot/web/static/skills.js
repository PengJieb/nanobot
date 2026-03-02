/* nanobot skills dashboard — logic pipeline flowchart view */
(function () {
    // -- Auth guard -----------------------------------------------------
    var token = localStorage.getItem("nanobot_token");
    if (!token) { window.location.href = "/login.html"; return; }

    // Init mermaid for dark theme
    mermaid.initialize({
        startOnLoad: false,
        theme: "dark",
        themeVariables: {
            primaryColor: "#3b82f6",
            primaryTextColor: "#f3f4f6",
            primaryBorderColor: "#60a5fa",
            lineColor: "#6b7280",
            secondaryColor: "#1f2937",
            tertiaryColor: "#111827",
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            fontSize: "14px"
        },
        flowchart: { curve: "basis", padding: 16 }
    });

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
    var mermaidCounter = 0;

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

    /** Render markdown, replacing ```mermaid blocks with placeholder divs. */
    function renderMarkdownWithMermaid(text) {
        // Replace ```mermaid ... ``` with placeholder divs before marked processes them
        var mermaidBlocks = [];
        var processed = text.replace(/```mermaid\s*\n([\s\S]*?)```/g, function (match, code) {
            var id = "mermaid-block-" + (++mermaidCounter);
            mermaidBlocks.push({ id: id, code: code.trim() });
            return '<div class="mermaid-placeholder" data-mermaid-id="' + id + '"></div>';
        });

        var html;
        try { html = marked.parse(processed); }
        catch (e) { html = processed.replace(/</g, "&lt;").replace(/\n/g, "<br>"); }

        return { html: html, blocks: mermaidBlocks };
    }

    /** Render all mermaid placeholders in a container into actual SVG flowcharts. */
    async function renderMermaidBlocks(container, blocks) {
        for (var i = 0; i < blocks.length; i++) {
            var b = blocks[i];
            var el = container.querySelector('[data-mermaid-id="' + b.id + '"]');
            if (!el) continue;
            try {
                var result = await mermaid.render(b.id, b.code);
                el.innerHTML =
                    '<div class="mermaid-chart">' + result.svg + '</div>';
            } catch (err) {
                // Fallback: show the mermaid source in a code block
                el.innerHTML =
                    '<pre class="bg-gray-800 rounded-lg p-4 overflow-x-auto text-sm text-gray-300">' +
                    '<code>' + b.code.replace(/</g, "&lt;") + '</code></pre>' +
                    '<p class="text-yellow-500 text-xs mt-1">Flowchart render failed — showing source</p>';
            }
        }
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

    // -- Load skill detail (logic pipeline flowchart view) --------------

    async function loadDetail(name) {
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

            // Build detail view
            var html = "";

            // Always show header with generate/regenerate button
            html += _pipelineHeader(data.logic);

            if (data.logic) {
                var rendered = renderMarkdownWithMermaid(data.logic);
                html += '<div class="pipeline-body">' + rendered.html + '</div>';
                detailContent.innerHTML = html;
                _bindButtons(name);
                await renderMermaidBlocks(detailContent, rendered.blocks);
            } else {
                html += '<div class="text-center py-16">';
                html += '<div class="mb-4">';
                html += '<svg class="w-16 h-16 mx-auto text-gray-600" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">';
                html += '<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z"/>';
                html += '</svg>';
                html += '</div>';
                html += '<p class="text-gray-500">No logic pipeline generated yet.</p>';
                html += '<p class="text-gray-600 text-sm mt-1">Click the button above to generate a flowchart.</p>';
                html += '</div>';
                detailContent.innerHTML = html;
                _bindButtons(name);
            }
        } catch (err) {
            detailContent.innerHTML = '<div class="text-red-400">Error: ' + err.message + '</div>';
        }
    }

    function _pipelineHeader(hasLogic) {
        var h = '<div class="flex items-center justify-between mb-5 pb-4 border-b border-gray-700">';
        h += '<h2 class="text-lg font-bold">Logic Pipeline</h2>';
        h += '<button id="gen-logic-btn" class="flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-md transition ';
        if (hasLogic) {
            // Subtle style for regenerate
            h += 'bg-gray-700 hover:bg-gray-600 text-gray-300 hover:text-white"';
            h += ' title="Regenerate pipeline via agent">';
            h += '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">';
            h += '<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>';
            h += '</svg>';
            h += 'Regenerate';
        } else {
            // Primary style for first generation
            h += 'bg-blue-600 hover:bg-blue-500 text-white"';
            h += ' title="Generate pipeline via agent">';
            h += '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">';
            h += '<path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z"/>';
            h += '</svg>';
            h += 'Generate Pipeline';
        }
        h += '</button>';
        h += '</div>';
        return h;
    }

    function _bindButtons(name) {
        var btn = document.getElementById("gen-logic-btn");
        if (btn) {
            btn.addEventListener("click", function () { generateLogic(name); });
        }
    }

    // -- Generate / refresh logic pipeline ------------------------------

    async function generateLogic(name) {
        // Show generating state
        detailContent.innerHTML =
            '<div class="flex flex-col items-center justify-center py-20">' +
            '<div class="typing-dots text-3xl text-blue-400 mb-4"><span>.</span><span>.</span><span>.</span></div>' +
            '<p class="text-gray-400 font-medium">Generating logic pipeline...</p>' +
            '<p class="text-gray-600 text-sm mt-1">The agent is analyzing this skill</p>' +
            '</div>';

        try {
            var resp = await fetch("/api/skills/" + encodeURIComponent(name) + "/generate-logic", {
                method: "POST",
                headers: authHeaders(),
            });
            if (handleUnauthorized(resp)) return;
            if (!resp.ok) throw new Error("Generation failed");

            // Update has_logic in the card list
            for (var i = 0; i < allSkills.length; i++) {
                if (allSkills[i].name === name) { allSkills[i].has_logic = true; break; }
            }

            // Reload detail with the fresh pipeline
            await loadDetail(name);
        } catch (err) {
            detailContent.innerHTML =
                _pipelineHeader(false) +
                '<div class="text-center py-12">' +
                '<p class="text-red-400 mb-4">Pipeline generation failed: ' + err.message + '</p>' +
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
