/* nanobot chat UI */
(function () {
    const messagesEl = document.getElementById("messages");
    const typingEl = document.getElementById("typing");
    const typingText = document.getElementById("typing-text");
    const form = document.getElementById("chat-form");
    const input = document.getElementById("input");
    const sendBtn = document.getElementById("send-btn");
    const newChatBtn = document.getElementById("new-chat-btn");

    let sessionKey = localStorage.getItem("nanobot_session") || null;
    let busy = false;

    // -- Helpers --------------------------------------------------------

    function getSessionKey() {
        if (!sessionKey) {
            sessionKey = "web:" + crypto.randomUUID().replace(/-/g, "").slice(0, 12);
            localStorage.setItem("nanobot_session", sessionKey);
        }
        return sessionKey;
    }

    function addMessage(role, html) {
        const wrapper = document.createElement("div");
        wrapper.className = "max-w-3xl mx-auto flex " + (role === "user" ? "justify-end" : "justify-start");

        const bubble = document.createElement("div");
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
        catch { return text.replace(/</g, "&lt;").replace(/\n/g, "<br>"); }
    }

    function escapeHtml(text) {
        const el = document.createElement("span");
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
        const text = input.value.trim();
        if (!text || busy) return;

        addMessage("user", escapeHtml(text));
        input.value = "";
        input.style.height = "auto";
        setBusy(true);
        setTyping(true, "nanobot is thinking");

        let assistantBubble = null;
        let fullContent = "";

        try {
            const resp = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text, session_key: getSessionKey() }),
            });

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                const lines = buffer.split("\n");
                buffer = lines.pop(); // keep incomplete line

                for (const line of lines) {
                    if (!line.startsWith("data: ")) continue;
                    let event;
                    try { event = JSON.parse(line.slice(6)); }
                    catch { continue; }

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

            // If no done event received, hide typing
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
            const resp = await fetch("/api/chat/new", { method: "POST" });
            const data = await resp.json();
            sessionKey = data.session_key;
            localStorage.setItem("nanobot_session", sessionKey);
        } catch {
            sessionKey = null;
            localStorage.removeItem("nanobot_session");
        }
        messagesEl.innerHTML = "";
        input.focus();
    });

    // -- Init -----------------------------------------------------------
    input.focus();
})();
