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

    // -- Helpers --------------------------------------------------------

    function generateId() {
        // Compatible fallback for crypto.randomUUID
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

    function addMessage(role, html) {
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

        addMessage("user", escapeHtml(text));
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
                            assistantBubble = addMessage("assistant", renderMarkdown(fullContent));
                        } else {
                            assistantBubble.innerHTML = renderMarkdown(fullContent);
                        }
                    } else if (event.type === "error") {
                        setTyping(false);
                        addMessage("assistant", "<span class='text-red-400'>Error: " + escapeHtml(event.content) + "</span>");
                    }
                }
            }

            setTyping(false);
        } catch (err) {
            setTyping(false);
            addMessage("assistant", "<span class='text-red-400'>Connection error: " + escapeHtml(err.message) + "</span>");
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
        messagesEl.innerHTML = "";
        input.focus();
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
    input.focus();
})();
