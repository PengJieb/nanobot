/* nanobot Apps gallery */
(function () {
    var token = localStorage.getItem("nanobot_token");
    if (!token) { window.location.href = "/login.html"; return; }

    var loadingEl = document.getElementById("loading");
    var emptyEl = document.getElementById("empty");
    var gridEl = document.getElementById("app-grid");
    var logoutBtn = document.getElementById("logout-btn");

    var LAYOUT_ICONS = {
        "single-page": "fa-file-lines",
        "dashboard": "fa-table-columns",
        "wizard": "fa-wand-magic-sparkles",
    };

    function authHeaders() {
        return { "Authorization": "Bearer " + token };
    }

    function handleUnauthorized(resp) {
        if (resp.status === 401) {
            localStorage.removeItem("nanobot_token");
            window.location.href = "/login.html";
            return true;
        }
        return false;
    }

    function formatDate(iso) {
        if (!iso) return "";
        try {
            return new Date(iso).toLocaleDateString(undefined, {
                year: "numeric", month: "short", day: "numeric",
            });
        } catch (e) { return ""; }
    }

    function renderCard(app) {
        var icon = LAYOUT_ICONS[app.layout_type] || "fa-cube";
        var card = document.createElement("div");
        card.className = "bg-gray-800 border border-gray-700 rounded-xl p-5 flex flex-col gap-3 " +
                         "hover:border-blue-500 transition cursor-pointer group";
        card.innerHTML =
            '<div class="flex items-start justify-between">' +
              '<div class="flex items-center gap-3">' +
                '<div class="w-10 h-10 rounded-lg bg-blue-900/50 flex items-center justify-center shrink-0">' +
                  '<i class="fa-solid ' + icon + ' text-blue-400"></i>' +
                '</div>' +
                '<div>' +
                  '<h3 class="font-semibold text-gray-100 group-hover:text-blue-400 transition leading-tight">' +
                    escapeHtml(app.title) +
                  '</h3>' +
                  '<span class="text-xs text-gray-500 capitalize">' + escapeHtml(app.layout_type) + '</span>' +
                '</div>' +
              '</div>' +
              '<button class="delete-btn text-gray-600 hover:text-red-400 transition text-sm opacity-0 group-hover:opacity-100" ' +
                      'data-id="' + escapeHtml(app.id) + '" title="Delete app">' +
                '<i class="fa-solid fa-trash"></i>' +
              '</button>' +
            '</div>' +
            '<p class="text-sm text-gray-400 line-clamp-2">' + escapeHtml(app.description || "No description.") + '</p>' +
            '<div class="flex items-center justify-between text-xs text-gray-500 mt-auto pt-1 border-t border-gray-700">' +
              '<span>' + app.component_count + ' component' + (app.component_count !== 1 ? "s" : "") + '</span>' +
              '<span>' + formatDate(app.created_at) + '</span>' +
            '</div>';

        card.addEventListener("click", function (e) {
            if (e.target.closest(".delete-btn")) return;
            window.location.href = "/app_viewer.html?id=" + encodeURIComponent(app.id);
        });

        var deleteBtn = card.querySelector(".delete-btn");
        deleteBtn.addEventListener("click", async function (e) {
            e.stopPropagation();
            if (!confirm('Delete "' + app.title + '"?')) return;
            try {
                var resp = await fetch("/api/app/" + encodeURIComponent(app.id), {
                    method: "DELETE",
                    headers: authHeaders(),
                });
                if (handleUnauthorized(resp)) return;
                if (resp.ok) {
                    card.remove();
                    if (!gridEl.children.length) { gridEl.classList.add("hidden"); emptyEl.classList.remove("hidden"); }
                }
            } catch (err) { alert("Delete failed: " + err.message); }
        });

        return card;
    }

    function escapeHtml(text) {
        var el = document.createElement("span");
        el.textContent = String(text || "");
        return el.innerHTML;
    }

    async function loadApps() {
        try {
            var resp = await fetch("/api/apps", { headers: authHeaders() });
            if (handleUnauthorized(resp)) return;
            var data = await resp.json();
            loadingEl.classList.add("hidden");

            if (!data.apps || !data.apps.length) {
                emptyEl.classList.remove("hidden");
                return;
            }

            gridEl.classList.remove("hidden");
            data.apps.forEach(function (app) {
                gridEl.appendChild(renderCard(app));
            });
        } catch (err) {
            loadingEl.innerHTML = '<p class="text-red-400">Failed to load apps: ' + err.message + '</p>';
        }
    }

    if (logoutBtn) {
        logoutBtn.addEventListener("click", function () {
            localStorage.removeItem("nanobot_token");
            window.location.href = "/login.html";
        });
    }

    loadApps();
})();
