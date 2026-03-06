/* nanobot App Builder — Q&A flow */
(function () {
    var token = localStorage.getItem("nanobot_token");
    if (!token) { window.location.href = "/login.html"; return; }

    var convEl = document.getElementById("conversation");
    var inputArea = document.getElementById("input-area");
    var generatingEl = document.getElementById("generating");
    var generatingText = document.getElementById("generating-text");
    var form = document.getElementById("answer-form");
    var answerInput = document.getElementById("answer-input");
    var submitBtn = document.getElementById("submit-btn");
    var progressBar = document.getElementById("progress-bar");
    var progressLabel = document.getElementById("progress-label");
    var progressPct = document.getElementById("progress-pct");
    var logoutBtn = document.getElementById("logout-btn");

    var sessionId = null;
    var totalQuestions = 10;
    var currentIndex = 0;
    var busy = false;

    function authHeaders(extra) {
        var h = { "Authorization": "Bearer " + token };
        if (extra) { for (var k in extra) h[k] = extra[k]; }
        return h;
    }

    function handleUnauthorized(resp) {
        if (resp.status === 401) {
            localStorage.removeItem("nanobot_token");
            window.location.href = "/login.html";
            return true;
        }
        return false;
    }

    function escapeHtml(text) {
        var el = document.createElement("span");
        el.textContent = String(text || "");
        return el.innerHTML;
    }

    function updateProgress(idx) {
        var pct = Math.round((idx / totalQuestions) * 100);
        progressBar.style.width = pct + "%";
        progressLabel.textContent = "Question " + (idx + 1) + " of " + totalQuestions;
        progressPct.textContent = pct + "%";
    }

    function addBot(text) {
        var row = document.createElement("div");
        row.className = "flex gap-3 items-start";
        row.innerHTML =
            '<div class="w-8 h-8 rounded-full bg-blue-900/60 flex items-center justify-center shrink-0 mt-0.5">' +
              '<i class="fa-solid fa-robot text-blue-400 text-sm"></i>' +
            '</div>' +
            '<div class="bg-gray-800 border border-gray-700 rounded-2xl rounded-tl-md px-4 py-3 max-w-lg">' +
              '<p class="text-gray-100">' + escapeHtml(text) + '</p>' +
            '</div>';
        convEl.appendChild(row);
        convEl.scrollTop = convEl.scrollHeight;
    }

    function addUser(text) {
        var row = document.createElement("div");
        row.className = "flex gap-3 items-start justify-end";
        row.innerHTML =
            '<div class="bg-blue-600 rounded-2xl rounded-tr-md px-4 py-3 max-w-lg">' +
              '<p class="text-white">' + escapeHtml(text) + '</p>' +
            '</div>';
        convEl.appendChild(row);
        convEl.scrollTop = convEl.scrollHeight;
    }

    function setBusy(v) {
        busy = v;
        submitBtn.disabled = v;
        answerInput.disabled = v;
    }

    async function startSession() {
        try {
            var resp = await fetch("/api/app/build/start", {
                method: "POST",
                headers: authHeaders(),
            });
            if (handleUnauthorized(resp)) return;
            var data = await resp.json();
            sessionId = data.session_id;
            totalQuestions = data.total_questions || 10;
            currentIndex = data.question_index || 0;
            updateProgress(currentIndex);
            addBot(data.question);
            answerInput.focus();
        } catch (err) {
            addBot("Failed to start session: " + err.message);
        }
    }

    form.addEventListener("submit", async function (e) {
        e.preventDefault();
        var answer = answerInput.value.trim();
        if (!answer || busy || !sessionId) return;

        addUser(answer);
        answerInput.value = "";
        setBusy(true);

        try {
            var resp = await fetch("/api/app/build/" + sessionId + "/answer", {
                method: "POST",
                headers: authHeaders({ "Content-Type": "application/json" }),
                body: JSON.stringify({ answer: answer }),
            });
            if (handleUnauthorized(resp)) return;
            var data = await resp.json();

            if (data.status === "complete") {
                updateProgress(totalQuestions);
                progressLabel.textContent = "All questions answered!";
                await generateApp();
            } else {
                currentIndex = data.question_index;
                updateProgress(currentIndex);
                addBot(data.question);
                setBusy(false);
                answerInput.focus();
            }
        } catch (err) {
            addBot("Error: " + err.message);
            setBusy(false);
        }
    });

    async function generateApp() {
        inputArea.classList.add("hidden");
        generatingEl.classList.remove("hidden");

        var messages = [
            "Designing your application...",
            "Defining components and layout...",
            "Wiring up interactions...",
            "Finalizing your app spec...",
        ];
        var msgIdx = 0;
        generatingText.textContent = messages[msgIdx];
        var msgTimer = setInterval(function () {
            msgIdx = (msgIdx + 1) % messages.length;
            generatingText.textContent = messages[msgIdx];
        }, 3000);

        try {
            var resp = await fetch("/api/app/build/" + sessionId + "/generate", {
                method: "POST",
                headers: authHeaders(),
            });
            if (handleUnauthorized(resp)) { clearInterval(msgTimer); return; }

            var reader = resp.body.getReader();
            var decoder = new TextDecoder();
            var buffer = "";

            while (true) {
                var chunk = await reader.read();
                if (chunk.done) break;
                buffer += decoder.decode(chunk.value, { stream: true });
                var lines = buffer.split("\n");
                buffer = lines.pop();

                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];
                    if (!line.startsWith("data: ")) continue;
                    var event;
                    try { event = JSON.parse(line.slice(6)); } catch (ex) { continue; }

                    if (event.type === "done") {
                        clearInterval(msgTimer);
                        window.location.href = "/app_viewer.html?id=" + encodeURIComponent(event.app_id);
                        return;
                    } else if (event.type === "error") {
                        clearInterval(msgTimer);
                        generatingEl.classList.add("hidden");
                        inputArea.classList.remove("hidden");
                        addBot("Error generating app: " + event.content);
                        setBusy(false);
                        return;
                    } else if (event.type === "progress") {
                        generatingText.textContent = event.content;
                    }
                }
            }
            clearInterval(msgTimer);
        } catch (err) {
            clearInterval(msgTimer);
            generatingEl.classList.add("hidden");
            inputArea.classList.remove("hidden");
            addBot("Error: " + err.message);
            setBusy(false);
        }
    }

    if (logoutBtn) {
        logoutBtn.addEventListener("click", function () {
            localStorage.removeItem("nanobot_token");
            window.location.href = "/login.html";
        });
    }

    startSession();
})();
