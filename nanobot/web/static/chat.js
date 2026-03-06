/* nanobot chat UI */
(function () {
    // -- Auth guard -----------------------------------------------------
    var token = localStorage.getItem("nanobot_token");
    if (!token) { window.location.href = "/login.html"; return; }

    var messagesEl = document.getElementById("messages");
    var typingEl = document.getElementById("typing");
    var typingText = document.getElementById("typing-text");
    var form = document.getElementById("chat-form");
    var input = document.getElementById("input");
    var sendBtn = document.getElementById("send-btn");
    var newChatBtn = document.getElementById("new-chat-btn");
    var logoutBtn = document.getElementById("logout-btn");

    var sessionKey = localStorage.getItem("nanobot_session") || null;
    var busy = false;

    // -- Chat history persistence (survives navigation, cleared on New Chat) --
    var HISTORY_KEY = "nanobot_chat_history";

    /** Append a message to sessionStorage history. */
    function saveMessage(role, content) {
        var history = _loadHistory();
        history.push({ role: role, content: content });
        sessionStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    }

    function _loadHistory() {
        try { return JSON.parse(sessionStorage.getItem(HISTORY_KEY)) || []; }
        catch (e) { return []; }
    }

    function clearHistory() {
        sessionStorage.removeItem(HISTORY_KEY);
    }

    /** Restore chat bubbles from sessionStorage on page load. */
    function restoreHistory() {
        var history = _loadHistory();
        for (var i = 0; i < history.length; i++) {
            var msg = history[i];
            if (msg.role === "user") {
                _addBubble("user", escapeHtml(msg.content));
            } else {
                _addBubble("assistant", renderMarkdown(msg.content));
            }
        }
    }

    // -- Helpers --------------------------------------------------------

    function generateId() {
        var arr = new Uint8Array(6);
        (window.crypto || window.msCrypto).getRandomValues(arr);
        return Array.from(arr, function (b) { return b.toString(16).padStart(2, "0"); }).join("");
    }

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

    function getSessionKey() {
        if (!sessionKey) {
            sessionKey = "web:" + generateId();
            localStorage.setItem("nanobot_session", sessionKey);
        }
        return sessionKey;
    }

    /** Add a bubble to the DOM (no persistence). */
    function _addBubble(role, html) {
        var wrapper = document.createElement("div");
        wrapper.className = "max-w-3xl mx-auto flex " + (role === "user" ? "justify-end" : "justify-start");

        var bubble = document.createElement("div");
        bubble.className = role === "user"
            ? "bg-blue-600 text-white rounded-2xl rounded-br-md px-4 py-2.5 max-w-[80%] msg-content"
            : "bg-gray-700 text-gray-100 rounded-2xl rounded-bl-md px-4 py-2.5 max-w-[80%] msg-content";
        bubble.innerHTML = html;

        wrapper.appendChild(bubble);
        messagesEl.appendChild(wrapper);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return bubble;
    }

    /** Add a bubble + persist to sessionStorage. */
    function addMessage(role, html, rawContent) {
        var bubble = _addBubble(role, html);
        if (rawContent !== undefined) {
            saveMessage(role, rawContent);
        }
        return bubble;
    }

    function renderMarkdown(text) {
        try { return marked.parse(text); }
        catch (e) { return text.replace(/</g, "&lt;").replace(/\n/g, "<br>"); }
    }

    function escapeHtml(text) {
        var el = document.createElement("span");
        el.textContent = text;
        return el.innerHTML;
    }

    function setTyping(show, text) {
        typingEl.classList.toggle("hidden", !show);
        if (text) typingText.textContent = text;
    }

    function setBusy(v) {
        busy = v;
        sendBtn.disabled = v;
        input.disabled = v;
    }

    // -- Auto-resize textarea -------------------------------------------

    input.addEventListener("input", function () {
        this.style.height = "auto";
        this.style.height = Math.min(this.scrollHeight, 200) + "px";
    });

    input.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            form.dispatchEvent(new Event("submit"));
        }
    });

    // -- Send message ---------------------------------------------------

    form.addEventListener("submit", async function (e) {
        e.preventDefault();
        var text = input.value.trim();
        if (!text || busy) return;

        // #app trigger — redirect to the application builder
        var lowerText = text.toLowerCase();
        if (lowerText === "#app" || lowerText.startsWith("#app ")) {
            window.location.href = "/app_builder.html";
            return;
        }

        addMessage("user", escapeHtml(text), text);
        input.value = "";
        input.style.height = "auto";
        setBusy(true);
        setTyping(true, "nanobot is thinking");

        var assistantBubble = null;
        var fullContent = "";

        try {
            var resp = await fetch("/api/chat", {
                method: "POST",
                headers: authHeaders({ "Content-Type": "application/json" }),
                body: JSON.stringify({ message: text, session_key: getSessionKey() }),
            });

            if (handleUnauthorized(resp)) return;

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
                    try { event = JSON.parse(line.slice(6)); }
                    catch (ex) { continue; }

                    if (event.type === "progress") {
                        setTyping(true, event.content || "working...");
                    } else if (event.type === "done") {
                        fullContent = event.content || "";
                        setTyping(false);
                        if (!assistantBubble) {
                            assistantBubble = addMessage("assistant", renderMarkdown(fullContent), fullContent);
                        } else {
                            assistantBubble.innerHTML = renderMarkdown(fullContent);
                            // Update last assistant message in history
                            saveMessage("assistant", fullContent);
                        }
                    } else if (event.type === "error") {
                        setTyping(false);
                        addMessage("assistant",
                            "<span class='text-red-400'>Error: " + escapeHtml(event.content) + "</span>",
                            "Error: " + event.content);
                    }
                }
            }

            setTyping(false);
        } catch (err) {
            setTyping(false);
            addMessage("assistant",
                "<span class='text-red-400'>Connection error: " + escapeHtml(err.message) + "</span>",
                "Connection error: " + err.message);
        }

        setBusy(false);
        input.focus();
    });

    // -- New chat -------------------------------------------------------

    newChatBtn.addEventListener("click", async function () {
        try {
            var resp = await fetch("/api/chat/new", {
                method: "POST",
                headers: authHeaders(),
            });
            if (handleUnauthorized(resp)) return;
            var data = await resp.json();
            sessionKey = data.session_key;
            localStorage.setItem("nanobot_session", sessionKey);
        } catch (ex) {
            sessionKey = null;
            localStorage.removeItem("nanobot_session");
        }
        clearHistory();
        messagesEl.innerHTML = "";
        input.focus();
    });

    // -- Logout ---------------------------------------------------------

    if (logoutBtn) {
        logoutBtn.addEventListener("click", function () {
            localStorage.removeItem("nanobot_token");
            localStorage.removeItem("nanobot_user");
            localStorage.removeItem("nanobot_session");
            clearHistory();
            window.location.href = "/login.html";
        });
    }

    // -- Init -----------------------------------------------------------
    restoreHistory();
    input.focus();
})();
