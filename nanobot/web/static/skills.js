/* nanobot skills dashboard */
(function () {
    const grid = document.getElementById("skills-grid");
    const searchInput = document.getElementById("search");
    const detailPanel = document.getElementById("detail-panel");
    const detailEmpty = document.getElementById("detail-empty");
    const detailName = document.getElementById("detail-name");
    const detailDesc = document.getElementById("detail-desc");
    const detailBadges = document.getElementById("detail-badges");
    const detailContent = document.getElementById("detail-content");

    let allSkills = [];
    let activeCard = null;

    // -- Helpers --------------------------------------------------------

    function badge(text, color) {
        return '<span class="inline-block text-xs font-medium px-2 py-0.5 rounded-full ' + color + '">' + text + '</span>';
    }

    function renderMarkdown(text) {
        try { return marked.parse(text); }
        catch { return text.replace(/</g, "&lt;").replace(/\n/g, "<br>"); }
    }

    // -- Render skill list ----------------------------------------------

    function renderCards(skills) {
        grid.innerHTML = "";
        skills.forEach(function (s) {
            const card = document.createElement("div");
            card.className = "skill-card cursor-pointer border border-gray-700 rounded-lg p-4";
            card.dataset.name = s.name;

            let badges = "";
            badges += badge(s.source, s.source === "builtin" ? "bg-purple-800 text-purple-200" : "bg-green-800 text-green-200");
            if (s.always_on) badges += " " + badge("always-on", "bg-yellow-800 text-yellow-200");
            if (!s.available) badges += " " + badge("unavailable", "bg-red-900 text-red-300");

            card.innerHTML =
                '<div class="font-semibold text-gray-100">' + s.name + '</div>' +
                '<div class="text-sm text-gray-400 mt-1 line-clamp-2">' + (s.description || "") + '</div>' +
                '<div class="flex gap-1 mt-2">' + badges + '</div>';

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
        detailContent.innerHTML = '<div class="text-gray-500">Loading...</div>';

        try {
            const resp = await fetch("/api/skills/" + encodeURIComponent(name));
            if (!resp.ok) { detailContent.innerHTML = '<div class="text-red-400">Failed to load skill.</div>'; return; }
            const data = await resp.json();

            detailName.textContent = data.name;
            detailDesc.textContent = data.description || "";

            let badges = "";
            badges += badge(data.source, data.source === "builtin" ? "bg-purple-800 text-purple-200" : "bg-green-800 text-green-200");
            if (data.always_on) badges += " " + badge("always-on", "bg-yellow-800 text-yellow-200");
            if (!data.available) badges += " " + badge("unavailable", "bg-red-900 text-red-300");
            detailBadges.innerHTML = badges;

            let html = '<h2 class="text-lg font-bold mb-3">SKILL.md</h2>' + renderMarkdown(data.content || "");

            if (data.logic) {
                html += '<hr class="my-6 border-gray-700">';
                html += '<h2 class="text-lg font-bold mb-3">LOGIC.md</h2>' + renderMarkdown(data.logic);
            } else {
                html += '<hr class="my-6 border-gray-700">';
                html += '<div class="flex items-center gap-3">';
                html += '<span class="text-gray-500">No LOGIC.md found.</span>';
                html += '<button id="gen-logic-btn" class="bg-blue-600 hover:bg-blue-500 text-white text-sm px-3 py-1.5 rounded-md transition">Generate</button>';
                html += '</div>';
            }

            detailContent.innerHTML = html;

            // Bind generate button
            var genBtn = document.getElementById("gen-logic-btn");
            if (genBtn) {
                genBtn.addEventListener("click", function () { generateLogic(name); });
            }
        } catch (err) {
            detailContent.innerHTML = '<div class="text-red-400">Error: ' + err.message + '</div>';
        }
    }

    // -- Generate LOGIC.md ----------------------------------------------

    async function generateLogic(name) {
        var btn = document.getElementById("gen-logic-btn");
        if (btn) { btn.disabled = true; btn.textContent = "Generating..."; }

        try {
            const resp = await fetch("/api/skills/" + encodeURIComponent(name) + "/generate-logic", { method: "POST" });
            if (!resp.ok) throw new Error("Generation failed");
            // Reload detail
            await loadDetail(name);
        } catch (err) {
            if (btn) { btn.textContent = "Failed - Retry"; btn.disabled = false; }
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

    // -- Init -----------------------------------------------------------

    async function init() {
        try {
            const resp = await fetch("/api/skills");
            const data = await resp.json();
            allSkills = data.skills || [];
            renderCards(allSkills);
        } catch (err) {
            grid.innerHTML = '<div class="text-red-400 p-4">Failed to load skills: ' + err.message + '</div>';
        }
    }

    init();
})();
