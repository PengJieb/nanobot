/* nanobot App Viewer — dynamic component renderer */
(function () {
    var token = localStorage.getItem("nanobot_token");
    if (!token) { window.location.href = "/login.html"; return; }

    var loadingState = document.getElementById("loading-state");
    var errorState = document.getElementById("error-state");
    var errorMsg = document.getElementById("error-msg");
    var appCanvas = document.getElementById("app-canvas");
    var appRoot = document.getElementById("app-root");
    var appTitlebar = document.getElementById("app-titlebar");
    var appTitleEl = document.getElementById("app-title");
    var appDescEl = document.getElementById("app-desc");
    var logoutBtn = document.getElementById("logout-btn");

    // Parse app id from URL
    var params = new URLSearchParams(window.location.search);
    var appId = params.get("id");

    // Application state (reactive)
    var state = {};
    // Registered component updater callbacks: { compId: fn(value) }
    var stateBindings = {};

    function authHeaders(extra) {
        var h = { "Authorization": "Bearer " + token };
        if (extra) for (var k in extra) h[k] = extra[k];
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
        el.textContent = String(text == null ? "" : text);
        return el.innerHTML;
    }

    // ---------------------------------------------------------------------------
    // State management
    // ---------------------------------------------------------------------------

    function getState(name) {
        return name ? state[name] : state;
    }

    function setState(name, value) {
        state[name] = value;
        console.log("setState called:", name, "=", value, "bindings:", stateBindings[name] ? stateBindings[name].length : 0);
        // Update all components bound to this variable
        if (stateBindings[name]) {
            stateBindings[name].forEach(function (fn) { try { fn(value); } catch (e) { console.error("Binding error:", e); } });
        }
    }

    function registerBinding(varName, updaterFn) {
        if (!varName) return;
        if (!stateBindings[varName]) stateBindings[varName] = [];
        stateBindings[varName].push(updaterFn);
    }

    // ---------------------------------------------------------------------------
    // Agent action call
    // ---------------------------------------------------------------------------

    async function callAgent(prompt, resultBind, indicatorEl) {
        if (indicatorEl) {
            indicatorEl.innerHTML =
                '<div class="app-typing">' +
                '<span class="app-typing-dots"><span>.</span><span>.</span><span>.</span></span>' +
                ' thinking...</div>';
            indicatorEl.classList.add("loading");
        }

        try {
            var resp = await fetch("/api/app/" + encodeURIComponent(appId) + "/action", {
                method: "POST",
                headers: authHeaders({ "Content-Type": "application/json" }),
                body: JSON.stringify({ prompt: prompt }),
            });
            if (handleUnauthorized(resp)) return;

            var reader = resp.body.getReader();
            var decoder = new TextDecoder();
            var buffer = "";
            var result = "";

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
                        result = event.content || "";
                    }
                }
            }

            if (resultBind) {
                // Strip markdown code fences if present
                var cleaned = result.trim();
                if (cleaned.startsWith("```")) {
                    cleaned = cleaned.replace(/^```[a-z]*\n?/, "");
                    cleaned = cleaned.replace(/\n?```$/, "");
                    cleaned = cleaned.trim();
                }

                // Try to parse as JSON array/object first, else store as string
                var parsed = cleaned;
                try {
                    var j = JSON.parse(cleaned);
                    if (Array.isArray(j) || (typeof j === "object" && j !== null)) parsed = j;
                } catch (e) {
                    parsed = cleaned;
                }
                console.log("Setting state with parsed value, type:", typeof parsed);
                setState(resultBind, parsed);
            }

            if (indicatorEl) {
                indicatorEl.classList.remove("loading");
                try {
                    indicatorEl.innerHTML = marked.parse(result);
                } catch (e) {
                    indicatorEl.textContent = result;
                }
            }
        } catch (err) {
            if (indicatorEl) {
                indicatorEl.classList.remove("loading");
                indicatorEl.textContent = "Error: " + err.message;
            }
        }
    }

    // ---------------------------------------------------------------------------
    // Resolve template: replace {{expression}} with evaluated values.
    // context is an optional object injected as second variable alongside state.
    // ---------------------------------------------------------------------------

    function resolveTemplate(template, context) {
        if (!template) return template;
        context = context || {};
        return String(template).replace(/\{\{(.+?)\}\}/g, function (match, expr) {
            try {
                var fn = new Function('state', 'context', 'return (' + expr + ')');
                var result = fn(state, context);
                if (result == null) return "";
                if (typeof result === "object") return JSON.stringify(result);
                return String(result);
            } catch (e) {
                console.warn("Template evaluation error:", expr, e);
                return match;
            }
        });
    }

    function extractStateVars(template) {
        if (!template) return [];
        var vars = [];
        var matches = String(template).match(/\{\{(.+?)\}\}/g);
        if (!matches) return [];
        matches.forEach(function(m) {
            var expr = m.match(/\{\{(.+?)\}\}/)[1];
            var stateRefs = expr.match(/state\.(\w+)/g);
            if (stateRefs) {
                stateRefs.forEach(function(ref) {
                    var varName = ref.replace('state.', '');
                    if (vars.indexOf(varName) === -1) vars.push(varName);
                });
            }
        });
        return vars;
    }

    // ---------------------------------------------------------------------------
    // Fire a single ComponentEvent with context
    // Used by sub-element handlers (table row/cell, chart data point) that need
    // to pass richer context beyond what the top-level wireEvents provides.
    // ---------------------------------------------------------------------------

    function fireEvent(ev, domEv, context) {
        if (!ev) return;
        context = context || {};
        if (ev.type === "local" && ev.local_code) {
            try {
                var value = context.value !== undefined ? context.value :
                            (domEv && domEv.target ? domEv.target.value : undefined);
                /* jshint evil:true */
                (new Function("state", "setState", "getState", "event", "value", "context",
                              ev.local_code))(state, setState, getState, domEv, value, context);
            } catch (e) {
                console.warn("Event handler error:", e);
            }
        } else if (ev.type === "agent" && ev.agent_prompt) {
            var prompt = resolveTemplate(ev.agent_prompt, context);
            var resultEl = ev.result_bind ? document.querySelector(
                '[data-state-bind="' + ev.result_bind + '"][data-result-display]') : null;
            callAgent(prompt, ev.result_bind, resultEl);
        }
    }

    // ---------------------------------------------------------------------------
    // Event wiring — attaches comp.events to an element.
    // Events named "row_click" and "cell_click" are skipped here; they are
    // handled explicitly inside the table renderRows function with row/cell context.
    // context is passed through to local_code and template resolution.
    // ---------------------------------------------------------------------------

    var SUB_ELEMENT_EVENTS = ["row_click", "cell_click"];

    function wireEvents(el, events, comp, context) {
        if (!events) return;
        context = context || {};
        console.log("wireEvents called for component:", comp.id, "events:", Object.keys(events));
        Object.keys(events).forEach(function (evName) {
            if (SUB_ELEMENT_EVENTS.indexOf(evName) !== -1) return;
            var ev = events[evName];
            if (!ev) return;
            var domEvent = evName === "click" ? "click" :
                           evName === "change" ? "change" :
                           evName === "submit" ? "submit" : evName;

            el.addEventListener(domEvent, function (domEv) {
                console.log("Event fired:", evName, "on component:", comp.id, "event type:", ev.type);
                fireEvent(ev, domEv, context);
            });
        });
    }

    // Mark a cell as clickable (cursor + hover ring) when it has a click event.
    function applyClickStyle(cell, events) {
        if (events && events.click) {
            cell.classList.add("has-click");
        }
    }

    // ---------------------------------------------------------------------------
    // Component factory
    // ---------------------------------------------------------------------------

    function buildCell(comp) {
        var layout = comp.layout || {};
        var colSpan = layout.colSpan || layout.col_span || 12;
        var col     = layout.col     != null ? layout.col     : 0;
        var row     = layout.row     != null ? layout.row     : 0;
        var rowSpan = layout.rowSpan || layout.row_span || 1;
        var cell = document.createElement("div");
        cell.className = "app-cell";
        cell.style.gridColumn = (col + 1) + " / span " + colSpan;
        cell.style.gridRow    = rowSpan > 1
            ? (row + 1) + " / span " + rowSpan
            : String(row + 1);
        cell.setAttribute("data-comp-id", comp.id);
        return cell;
    }

    function buildComponent(comp) {
        var cell = buildCell(comp);
        var inner;

        switch (comp.type) {

            case "heading": {
                var level = (comp.properties.level || 1);
                inner = document.createElement("h" + level);
                inner.className = level === 1 ? "text-2xl font-bold app-comp-heading" :
                                   level === 2 ? "text-xl font-bold app-comp-heading" :
                                   "text-lg font-semibold app-comp-heading";
                var text = comp.properties.text || comp.label || "";
                inner.textContent = resolveTemplate(text);
                extractStateVars(text).forEach(function(varName) {
                    registerBinding(varName, function() { inner.textContent = resolveTemplate(text); });
                });
                break;
            }

            case "text": {
                inner = document.createElement("div");
                inner.className = "app-result-box msg-content";
                inner.setAttribute("data-state-bind", comp.bind || "");
                console.log("Creating text component:", comp.id, "bind:", comp.bind, "has data-result-display:", !!comp.bind);
                if (comp.bind) {
                    inner.setAttribute("data-result-display", "1");
                    registerBinding(comp.bind, function (val) {
                        console.log("Text component binding triggered for:", comp.bind, "value type:", typeof val);
                        if (typeof val === "string") {
                            try { inner.innerHTML = marked.parse(val); }
                            catch (e) { inner.textContent = val; }
                        } else if (Array.isArray(val)) {
                            inner.textContent = val.join("\n");
                        } else if (val != null) {
                            inner.textContent = JSON.stringify(val, null, 2);
                        }
                    });
                    var initVal = state[comp.bind];
                    if (initVal != null) {
                        try { inner.innerHTML = marked.parse(String(initVal)); }
                        catch (e) { inner.textContent = String(initVal); }
                    } else {
                        var content = resolveTemplate(comp.properties.content || "");
                        try { inner.innerHTML = marked.parse(content); }
                        catch (e) { inner.textContent = content; }
                    }
                } else {
                    var content = resolveTemplate(comp.properties.content || comp.label || "");
                    try { inner.innerHTML = marked.parse(content); }
                    catch (e) { inner.textContent = content; }
                    extractStateVars(comp.properties.content || comp.label || "").forEach(function(varName) {
                        registerBinding(varName, function() {
                            var updated = resolveTemplate(comp.properties.content || comp.label || "");
                            try { inner.innerHTML = marked.parse(updated); }
                            catch (e) { inner.textContent = updated; }
                        });
                    });
                }
                break;
            }

            case "input": {
                var wrapper = document.createElement("div");
                if (comp.label) {
                    var lbl = document.createElement("div");
                    lbl.className = "app-label";
                    lbl.textContent = comp.label;
                    wrapper.appendChild(lbl);
                }
                inner = document.createElement("input");
                inner.type = comp.properties.inputType || "text";
                inner.className = "app-input";
                inner.placeholder = comp.properties.placeholder || "";
                if (comp.bind) {
                    inner.value = state[comp.bind] || "";
                    inner.addEventListener("input", function () { setState(comp.bind, inner.value); });
                    registerBinding(comp.bind, function (v) { if (inner.value !== String(v || "")) inner.value = v || ""; });
                }
                wrapper.appendChild(inner);
                cell.appendChild(wrapper);
                wireEvents(cell, comp.events, comp);
                applyClickStyle(cell, comp.events);
                return cell;
            }

            case "textarea": {
                var wrapper = document.createElement("div");
                if (comp.label) {
                    var lbl = document.createElement("div");
                    lbl.className = "app-label";
                    lbl.textContent = comp.label;
                    wrapper.appendChild(lbl);
                }
                inner = document.createElement("textarea");
                inner.className = "app-textarea";
                inner.rows = comp.properties.rows || 4;
                inner.placeholder = comp.properties.placeholder || "";
                if (comp.bind) {
                    inner.value = state[comp.bind] || "";
                    inner.addEventListener("input", function () { setState(comp.bind, inner.value); });
                    registerBinding(comp.bind, function (v) { if (inner.value !== String(v || "")) inner.value = String(v || ""); });
                }
                wrapper.appendChild(inner);
                cell.appendChild(wrapper);
                wireEvents(cell, comp.events, comp);
                applyClickStyle(cell, comp.events);
                return cell;
            }

            case "select": {
                var wrapper = document.createElement("div");
                if (comp.label) {
                    var lbl = document.createElement("div");
                    lbl.className = "app-label";
                    lbl.textContent = comp.label;
                    wrapper.appendChild(lbl);
                }
                inner = document.createElement("select");
                inner.className = "app-select";
                var opts = comp.properties.options || [];
                opts.forEach(function (opt) {
                    var o = document.createElement("option");
                    o.value = typeof opt === "string" ? opt : (opt.value || "");
                    o.textContent = typeof opt === "string" ? opt : (opt.label || opt.value || "");
                    inner.appendChild(o);
                });
                if (comp.bind) {
                    inner.value = state[comp.bind] || "";
                    inner.addEventListener("change", function () { setState(comp.bind, inner.value); });
                    registerBinding(comp.bind, function (v) { inner.value = v || ""; });
                }
                wrapper.appendChild(inner);
                cell.appendChild(wrapper);
                wireEvents(cell, comp.events, comp);
                applyClickStyle(cell, comp.events);
                return cell;
            }

            case "button": {
                inner = document.createElement("button");
                inner.className = "app-btn " + (comp.properties.variant || "primary");
                inner.textContent = comp.label || "Click";
                break;
            }

            case "checkbox": {
                var wrapper = document.createElement("label");
                wrapper.className = "flex items-center gap-2 cursor-pointer select-none";
                var cb = document.createElement("input");
                cb.type = "checkbox";
                cb.className = "w-4 h-4 rounded accent-blue-500 cursor-pointer";
                if (comp.bind) {
                    cb.checked = !!state[comp.bind];
                    cb.addEventListener("change", function () { setState(comp.bind, cb.checked); });
                    registerBinding(comp.bind, function (v) { cb.checked = !!v; });
                }
                var lblEl = document.createElement("span");
                lblEl.className = "text-sm text-gray-300";
                lblEl.textContent = comp.label || comp.properties.checked_label || "Enable";
                wrapper.appendChild(cb);
                wrapper.appendChild(lblEl);
                cell.appendChild(wrapper);
                wireEvents(cell, comp.events, comp);
                applyClickStyle(cell, comp.events);
                return cell;
            }

            case "slider": {
                var wrapper = document.createElement("div");
                if (comp.label) {
                    var lbl = document.createElement("div");
                    lbl.className = "app-label";
                    lbl.textContent = comp.label;
                    wrapper.appendChild(lbl);
                }
                var row = document.createElement("div");
                row.className = "flex items-center gap-2";
                inner = document.createElement("input");
                inner.type = "range";
                inner.className = "app-slider flex-1";
                inner.min = comp.properties.min != null ? comp.properties.min : 0;
                inner.max = comp.properties.max != null ? comp.properties.max : 100;
                inner.step = comp.properties.step != null ? comp.properties.step : 1;
                var valDisplay = document.createElement("span");
                valDisplay.className = "slider-value w-10 text-right";
                if (comp.bind) {
                    inner.value = state[comp.bind] != null ? state[comp.bind] : inner.min;
                    valDisplay.textContent = inner.value;
                    inner.addEventListener("input", function () {
                        setState(comp.bind, Number(inner.value));
                        valDisplay.textContent = inner.value;
                    });
                    registerBinding(comp.bind, function (v) { inner.value = v; valDisplay.textContent = v; });
                } else {
                    inner.value = inner.min;
                    valDisplay.textContent = inner.value;
                    inner.addEventListener("input", function () { valDisplay.textContent = inner.value; });
                }
                row.appendChild(inner);
                row.appendChild(valDisplay);
                wrapper.appendChild(row);
                cell.appendChild(wrapper);
                wireEvents(cell, comp.events, comp);
                applyClickStyle(cell, comp.events);
                return cell;
            }

            case "table": {
                var wrapper = document.createElement("div");
                wrapper.className = "overflow-auto rounded-lg border border-gray-700";
                wrapper.style.maxHeight = "24rem";
                wrapper.setAttribute("data-state-bind", comp.bind || "");
                var table = document.createElement("table");
                table.className = "app-table";
                var thead = document.createElement("thead");
                var tr = document.createElement("tr");
                var cols = comp.properties.columns || [];
                cols.forEach(function (col) {
                    var th = document.createElement("th");
                    th.textContent = col.label || col.key || col;
                    tr.appendChild(th);
                });
                thead.appendChild(tr);
                var tbody = document.createElement("tbody");

                // Interaction config from properties
                var rowClickable = !!(comp.properties.row_clickable || (comp.events && comp.events.row_click));
                var rowClickBind = comp.properties.row_click_bind || "";
                var cellClickBind = comp.properties.cell_click_bind || "";
                var cellEditable = !!comp.properties.cell_editable;
                var editableCols = comp.properties.editable_columns || null;

                function renderRows(data) {
                    tbody.innerHTML = "";
                    var rows = Array.isArray(data) ? data : (data ? [data] : []);
                    if (!rows.length) {
                        var emptyTr = document.createElement("tr");
                        var td = document.createElement("td");
                        td.colSpan = cols.length || 1;
                        td.className = "text-center text-gray-500 py-4";
                        td.textContent = "No data";
                        emptyTr.appendChild(td);
                        tbody.appendChild(emptyTr);
                        return;
                    }
                    rows.forEach(function (rowData, rowIndex) {
                        var tr2 = document.createElement("tr");

                        // Row-level click
                        if (rowClickable) {
                            tr2.classList.add("row-clickable");
                            tr2.addEventListener("click", function (domEv) {
                                // Deselect previous, select current
                                tbody.querySelectorAll("tr.row-selected").forEach(function(r) { r.classList.remove("row-selected"); });
                                tr2.classList.add("row-selected");
                                if (rowClickBind) setState(rowClickBind, rowData);
                                if (comp.events && comp.events.row_click) {
                                    fireEvent(comp.events.row_click, domEv, { rowData: rowData, rowIndex: rowIndex });
                                }
                            });
                        }

                        cols.forEach(function (col) {
                            var td = document.createElement("td");
                            var key = col.key || col;
                            var rawVal = typeof rowData === "object" ? (rowData[key] != null ? rowData[key] : "") : rowData;
                            var displayVal = typeof rawVal === "object" ? JSON.stringify(rawVal) : String(rawVal);
                            td.textContent = displayVal;

                            var isEditable = cellEditable && (!editableCols || editableCols.indexOf(key) !== -1);
                            var hasCellClick = !!(cellClickBind || (comp.events && comp.events.cell_click));

                            if (isEditable) {
                                // Inline cell editing
                                td.classList.add("cell-editable");
                                (function (capturedKey, capturedRowIndex, capturedRowData) {
                                    td.addEventListener("click", function (domEv) {
                                        domEv.stopPropagation();
                                        if (td.querySelector(".app-table-cell-input")) return;
                                        var origVal = td.textContent;
                                        var inp = document.createElement("input");
                                        inp.className = "app-table-cell-input";
                                        inp.value = origVal;
                                        td.textContent = "";
                                        td.appendChild(inp);
                                        inp.focus();
                                        inp.select();

                                        function commitEdit() {
                                            var newVal = inp.value;
                                            if (comp.bind && Array.isArray(state[comp.bind])) {
                                                var arr = state[comp.bind].slice();
                                                if (typeof arr[capturedRowIndex] === "object" && arr[capturedRowIndex] !== null) {
                                                    arr[capturedRowIndex] = Object.assign({}, arr[capturedRowIndex]);
                                                    arr[capturedRowIndex][capturedKey] = newVal;
                                                } else {
                                                    arr[capturedRowIndex] = newVal;
                                                }
                                                setState(comp.bind, arr);
                                            } else {
                                                td.textContent = newVal;
                                            }
                                        }

                                        inp.addEventListener("blur", commitEdit);
                                        inp.addEventListener("keydown", function (e) {
                                            if (e.key === "Enter") { e.preventDefault(); inp.blur(); }
                                            if (e.key === "Escape") { td.textContent = origVal; }
                                        });
                                    });
                                })(key, rowIndex, rowData);

                            } else if (hasCellClick) {
                                // Cell click → state + optional event
                                td.classList.add("cell-clickable");
                                (function (capturedKey, capturedRowIndex, capturedDisplayVal, capturedRowData) {
                                    td.addEventListener("click", function (domEv) {
                                        domEv.stopPropagation();
                                        var ctx = {
                                            rowIndex: capturedRowIndex,
                                            colKey: capturedKey,
                                            value: capturedDisplayVal,
                                            rowData: capturedRowData
                                        };
                                        if (cellClickBind) setState(cellClickBind, ctx);
                                        if (comp.events && comp.events.cell_click) {
                                            fireEvent(comp.events.cell_click, domEv, ctx);
                                        }
                                    });
                                })(key, rowIndex, displayVal, rowData);
                            }

                            tr2.appendChild(td);
                        });
                        tbody.appendChild(tr2);
                    });
                }

                if (comp.bind) {
                    registerBinding(comp.bind, renderRows);
                    renderRows(state[comp.bind]);
                }

                table.appendChild(thead);
                table.appendChild(tbody);
                wrapper.appendChild(table);
                cell.appendChild(wrapper);
                // Wire cell-level events (row_click/cell_click are handled above, skipped by wireEvents)
                wireEvents(cell, comp.events, comp);
                applyClickStyle(cell, comp.events);
                return cell;
            }

            case "chart": {
                var wrapper = document.createElement("div");
                wrapper.className = "bg-gray-800 border border-gray-700 rounded-lg p-4";
                if (comp.label) {
                    var lbl = document.createElement("div");
                    lbl.className = "text-sm font-medium text-gray-400 mb-3";
                    lbl.textContent = comp.label;
                    wrapper.appendChild(lbl);
                }
                var canvas = document.createElement("canvas");
                canvas.style.maxHeight = "300px";
                wrapper.appendChild(canvas);
                cell.appendChild(wrapper);

                var chartInst = null;
                var xKey = comp.properties.x_key || "label";
                var yKey = comp.properties.y_key || "value";
                var chartType = comp.properties.chart_type || "bar";
                var chartClickEv = comp.events && comp.events.click ? comp.events.click : null;

                function renderChart(data) {
                    var rows = Array.isArray(data) ? data : [];
                    var labels = rows.map(function (r) { return r[xKey] != null ? String(r[xKey]) : ""; });
                    var values = rows.map(function (r) { return Number(r[yKey]) || 0; });

                    // Chart.js onClick — passes data point context to the event handler
                    var onClickFn = chartClickEv ? function (event, elements) {
                        if (!elements.length) return;
                        var el = elements[0];
                        var ctx = {
                            dataIndex: el.index,
                            label: labels[el.index] || "",
                            value: values[el.index] || 0
                        };
                        fireEvent(chartClickEv, event, ctx);
                    } : undefined;

                    if (chartInst) {
                        chartInst.data.labels = labels;
                        chartInst.data.datasets[0].data = values;
                        if (onClickFn) chartInst.options.onClick = onClickFn;
                        chartInst.update();
                    } else {
                        chartInst = new Chart(canvas, {
                            type: chartType,
                            data: {
                                labels: labels,
                                datasets: [{
                                    label: comp.label || "Value",
                                    data: values,
                                    backgroundColor: "rgba(59,130,246,0.6)",
                                    borderColor: "rgba(59,130,246,0.9)",
                                    borderWidth: 1,
                                }],
                            },
                            options: {
                                responsive: true,
                                onClick: onClickFn,
                                plugins: { legend: { labels: { color: "#9ca3af" } } },
                                scales: chartType !== "pie" ? {
                                    x: { ticks: { color: "#9ca3af" }, grid: { color: "#374151" } },
                                    y: { ticks: { color: "#9ca3af" }, grid: { color: "#374151" } },
                                } : undefined,
                            },
                        });
                        if (chartClickEv) canvas.style.cursor = "pointer";
                    }
                }

                if (comp.bind) {
                    registerBinding(comp.bind, renderChart);
                    renderChart(state[comp.bind] || []);
                }
                // Wire non-click events to cell; chart click is handled via Chart.js onClick above
                var nonClickEvents = {};
                if (comp.events) {
                    Object.keys(comp.events).forEach(function (k) {
                        if (k !== "click") nonClickEvents[k] = comp.events[k];
                    });
                }
                wireEvents(cell, nonClickEvents, comp);
                return cell;
            }

            case "card": {
                inner = document.createElement("div");
                var color = comp.properties.color || "";
                inner.className = "app-card" + (color ? " color-" + color : "");

                if (color) {
                    var overlay = document.createElement("div");
                    overlay.className = "app-card-overlay color-" + color;
                    inner.appendChild(overlay);
                }

                var content = document.createElement("div");
                content.className = "app-card-content";

                if (comp.properties.icon || comp.properties.title) {
                    var header = document.createElement("div");
                    header.className = "app-card-header";
                    if (comp.properties.icon) {
                        var iconEl = document.createElement("i");
                        iconEl.className = comp.properties.icon + " app-card-icon" + (color ? " color-" + color : "");
                        header.appendChild(iconEl);
                    }
                    if (comp.properties.title) {
                        var titleEl = document.createElement("div");
                        titleEl.className = "app-card-title" + (color ? " gradient-text-" + color : " font-semibold text-gray-100");
                        var titleText = comp.properties.title;
                        titleEl.textContent = resolveTemplate(titleText);
                        extractStateVars(titleText).forEach(function(varName) {
                            registerBinding(varName, function() { titleEl.textContent = resolveTemplate(titleText); });
                        });
                        header.appendChild(titleEl);
                    }
                    content.appendChild(header);
                }

                var bodyEl = document.createElement("div");
                bodyEl.className = "app-card-body";
                var bodyText = comp.properties.body || comp.label || "";
                bodyEl.textContent = resolveTemplate(bodyText);
                extractStateVars(bodyText).forEach(function(varName) {
                    registerBinding(varName, function() { bodyEl.textContent = resolveTemplate(bodyText); });
                });
                content.appendChild(bodyEl);
                inner.appendChild(content);
                break;
            }

            case "divider": {
                inner = document.createElement("hr");
                inner.className = "app-divider";
                break;
            }

            case "image": {
                inner = document.createElement("img");
                inner.className = "max-w-full rounded-lg";
                inner.src = comp.properties.src || "";
                inner.alt = comp.label || "";
                break;
            }

            case "stat": {
                inner = document.createElement("div");
                var color = comp.properties.color || "";
                inner.className = "app-card app-stat" + (color ? " color-" + color : "");

                if (color) {
                    var overlay = document.createElement("div");
                    overlay.className = "app-card-overlay color-" + color;
                    inner.appendChild(overlay);
                }

                var content = document.createElement("div");
                content.className = "app-card-content";

                var numEl = document.createElement("div");
                numEl.className = "app-stat-number" + (color ? " gradient-text-" + color : "");
                var numText = comp.properties.number || comp.label || "0";
                numEl.textContent = resolveTemplate(numText);
                extractStateVars(numText).forEach(function(v) {
                    registerBinding(v, function() { numEl.textContent = resolveTemplate(numText); });
                });
                content.appendChild(numEl);

                if (comp.properties.stat_label) {
                    var lblEl = document.createElement("div");
                    lblEl.className = "app-stat-label";
                    lblEl.textContent = comp.properties.stat_label;
                    content.appendChild(lblEl);
                }

                if (comp.properties.description) {
                    var descEl = document.createElement("div");
                    descEl.className = "app-stat-desc";
                    descEl.textContent = comp.properties.description;
                    content.appendChild(descEl);
                }

                inner.appendChild(content);
                break;
            }

            default: {
                inner = document.createElement("div");
                inner.className = "text-xs text-gray-500 italic";
                inner.textContent = "[unknown component: " + comp.type + "]";
            }
        }

        // Universal tail — runs for all components that set `inner` without early-returning.
        // Events are wired to the outer cell so ANY component type can act as an interactive trigger.
        if (inner) {
            cell.appendChild(inner);
        }
        wireEvents(cell, comp.events, comp);
        applyClickStyle(cell, comp.events);
        return cell;
    }

    // ---------------------------------------------------------------------------
    // Load and render the app
    // ---------------------------------------------------------------------------

    async function loadApp() {
        if (!appId) {
            errorMsg.textContent = "No app ID specified.";
            loadingState.classList.add("hidden");
            errorState.classList.remove("hidden");
            return;
        }

        try {
            var resp = await fetch("/api/app/" + encodeURIComponent(appId), {
                headers: authHeaders(),
            });
            if (handleUnauthorized(resp)) return;
            if (!resp.ok) {
                throw new Error("HTTP " + resp.status);
            }
            var spec = await resp.json();

            // Set page title
            document.title = "nanobot - " + (spec.title || "App");
            appTitleEl.textContent = spec.title || "App";
            appDescEl.textContent = spec.description || "";
            appTitlebar.classList.remove("hidden");

            // Apply theme to body
            var theme = (spec.layout && spec.layout.theme) || "dark";
            if (theme === "light") {
                document.body.classList.add("app-theme-light");
                document.body.classList.remove("bg-gray-900", "text-gray-100");
                document.body.classList.add("text-gray-900");
            } else {
                document.body.classList.remove("app-theme-light", "text-gray-900");
                document.body.classList.add("bg-gray-900", "text-gray-100");
            }

            // Apply custom theme_colors as CSS variables on #app-canvas
            var canvas = document.getElementById("app-canvas");
            if (spec.theme_colors && typeof spec.theme_colors === "object") {
                Object.keys(spec.theme_colors).forEach(function(key) {
                    canvas.style.setProperty(key, String(spec.theme_colors[key]));
                });
            }

            // Show color palette badge if spec has a named palette
            if (spec.color) {
                var badge = document.getElementById("app-color-badge");
                var colorNameEl = document.getElementById("app-color-name");
                if (badge && colorNameEl) {
                    colorNameEl.textContent = spec.color;
                    badge.classList.remove("hidden");
                }
            }

            // Initialize state from spec (preserve existing values)
            var vars = (spec.state && spec.state.variables) || [];
            vars.forEach(function (v) {
                if (state[v.name] === undefined) {
                    state[v.name] = v.default != null ? v.default : (
                        v.type === "array" ? [] :
                        v.type === "object" ? {} :
                        v.type === "boolean" ? false :
                        v.type === "number" ? 0 : ""
                    );
                }
            });

            // Clear old bindings and DOM
            stateBindings = {};
            appRoot.innerHTML = "";

            // Sort components by row then col
            var comps = (spec.components || []).slice();
            comps.sort(function (a, b) {
                var ar = (a.layout || {}).row || 0;
                var br = (b.layout || {}).row || 0;
                if (ar !== br) return ar - br;
                return ((a.layout || {}).col || 0) - ((b.layout || {}).col || 0);
            });

            comps.forEach(function (comp) {
                var cell = buildComponent(comp);
                appRoot.appendChild(cell);
            });

            loadingState.classList.add("hidden");
            appCanvas.classList.remove("hidden");

        } catch (err) {
            errorMsg.textContent = "Failed to load app: " + err.message;
            loadingState.classList.add("hidden");
            errorState.classList.remove("hidden");
        }
    }

    if (logoutBtn) {
        logoutBtn.addEventListener("click", function () {
            localStorage.removeItem("nanobot_token");
            window.location.href = "/login.html";
        });
    }

    // Feedback handler
    var feedbackBtn = document.getElementById("feedback-btn");
    var feedbackInput = document.getElementById("feedback-input");

    if (feedbackBtn && feedbackInput) {
        feedbackBtn.addEventListener("click", async function() {
            var feedback = feedbackInput.value.trim();
            if (!feedback) return;

            feedbackBtn.disabled = true;
            feedbackBtn.textContent = "Regenerating...";

            try {
                var resp = await fetch("/api/app/" + appId + "/improve", {
                    method: "POST",
                    headers: authHeaders({"Content-Type": "application/json"}),
                    body: JSON.stringify({feedback: feedback})
                });

                if (handleUnauthorized(resp)) return;

                if (resp.ok) {
                    feedbackInput.value = "";
                    await loadApp();
                } else {
                    alert("Failed to regenerate app");
                }
            } catch (err) {
                alert("Error: " + err.message);
            } finally {
                feedbackBtn.disabled = false;
                feedbackBtn.textContent = "Regenerate";
            }
        });
    }

    loadApp();
})();
