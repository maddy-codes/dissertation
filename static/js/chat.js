document.addEventListener("DOMContentLoaded", () => {
    const tenantId = CHAT_CONFIG.tenantId;
    if (!tenantId) return;

    let currentSessionId = CHAT_CONFIG.sessionId || null;

    const messagesCont = document.getElementById("chat-messages");
    const emptyState = document.getElementById("chat-empty-state");
    const form = document.getElementById("chat-form");
    const input = document.getElementById("chat-input");
    const sendBtn = document.getElementById("btn-send");
    const tenantSelect = document.getElementById("tenant-select");
    const newChatBtn = document.getElementById("btn-new-chat");
    const historyBtn = document.getElementById("btn-history");
    const historyPanel = document.getElementById("history-panel");
    const canvasBody = document.getElementById("canvas-body");
    const canvasEmptyState = document.getElementById("canvas-empty-state");
    const canvasHistory = document.getElementById("canvas-history");
    const memoryBody = document.getElementById("memory-body");
    const memoryEmptyState = document.getElementById("memory-empty-state");
    const memoryForm = document.getElementById("memory-form");
    const memoryInput = document.getElementById("memory-input");
    const artifactModal = document.getElementById("artifact-modal");
    const artifactModalBody = document.getElementById("artifact-modal-body");
    const artifactModalClose = document.getElementById("artifact-modal-close");

    const refreshIcons = () => { if (window.lucide) lucide.createIcons(); };

    const canvasChartRef = { chart: null };
    const modalChartRef = { chart: null };
    const artifactHistory = [];

    const hideEmptyState = () => { if (emptyState) emptyState.remove(); };

    const setSessionId = (id) => {
        currentSessionId = id || null;
        const url = new URL(window.location.href);
        if (currentSessionId) url.searchParams.set("session_id", currentSessionId);
        else url.searchParams.delete("session_id");
        window.history.replaceState(null, "", url.toString());
    };

    const renderMarkdown = (text) => {
        if (window.marked && window.DOMPurify) {
            return DOMPurify.sanitize(marked.parse(text || "", { breaks: true }));
        }
        return null;
    };

    const bubble = (role, text) => {
        const wrap = document.createElement("div");
        wrap.className = role === "user"
            ? "self-end max-w-[80%] bg-primary/20 border border-primary/30 rounded-lg px-5 py-3.5"
            : "self-start max-w-[80%] bg-neutral border border-border-hairline rounded-lg px-5 py-3.5";

        if (role === "assistant") {
            const div = document.createElement("div");
            div.className = "chat-markdown text-sm font-medium text-on-surface leading-relaxed";
            const html = renderMarkdown(text);
            if (html !== null) div.innerHTML = html;
            else div.textContent = text;
            wrap.appendChild(div);
        } else {
            const p = document.createElement("p");
            p.className = "text-sm font-medium text-on-surface whitespace-pre-wrap leading-relaxed";
            p.textContent = text;
            wrap.appendChild(p);
        }
        return wrap;
    };

    const toolLogDetails = (toolLog) => {
        if (!toolLog || toolLog.length === 0) return null;
        const details = document.createElement("details");
        details.className = "mt-3";
        const summary = document.createElement("summary");
        summary.className = "cursor-pointer font-mono text-[9px] uppercase tracking-widest text-on-surface-muted hover:text-secondary transition-colors";
        summary.textContent = `Used ${toolLog.length} Xero lookup${toolLog.length === 1 ? "" : "s"}`;
        details.appendChild(summary);
        const list = document.createElement("ul");
        list.className = "mt-2 flex flex-col gap-1";
        toolLog.forEach((line) => {
            const li = document.createElement("li");
            li.className = "font-mono text-[10px] text-on-surface-muted";
            li.textContent = `→ ${line}`;
            list.appendChild(li);
        });
        details.appendChild(list);
        return details;
    };

    const openArtifactModal = (artifact) => {
        renderArtifactInto(artifactModalBody, artifact, modalChartRef, false);
        artifactModal.classList.remove("hidden");
        artifactModal.classList.add("flex");
        setTimeout(() => artifactModal.classList.add("opacity-100"), 10);
    };

    const closeArtifactModal = () => {
        artifactModal.classList.remove("opacity-100");
        setTimeout(() => artifactModal.classList.add("hidden"), 300);
    };

    if (artifactModalClose) artifactModalClose.addEventListener("click", closeArtifactModal);
    if (artifactModal) {
        artifactModal.addEventListener("click", (e) => { if (e.target === artifactModal) closeArtifactModal(); });
    }

    // container must have relative positioning for the expand button to anchor to.
    // chartRef is a small {chart: null} box the caller owns, so each rendered
    // surface (canvas panel / an inline card / the modal) manages its own
    // Chart.js instance without destroying anyone else's.
    function renderArtifactInto(container, artifact, chartRef, showExpand = true) {
        container.innerHTML = "";

        if (showExpand) {
            const expandBtn = document.createElement("button");
            expandBtn.type = "button";
            expandBtn.title = "Expand";
            expandBtn.className = "absolute top-3 right-3 z-10 text-on-surface-muted hover:text-secondary transition-colors bg-surface/80 rounded-full p-1.5";
            const icon = document.createElement("i");
            icon.setAttribute("data-lucide", "maximize-2");
            icon.className = "w-3.5 h-3.5";
            expandBtn.appendChild(icon);
            expandBtn.addEventListener("click", () => openArtifactModal(artifact));
            container.appendChild(expandBtn);
        }

        const title = document.createElement("h4");
        title.className = "font-mono text-[10px] uppercase tracking-[0.2em] text-secondary mb-4 pr-8";
        title.textContent = artifact.title || "Artefact";
        container.appendChild(title);

        if (artifact.kind === "table") {
            const rowUrls = artifact.row_urls || [];
            const hasLinks = rowUrls.some(Boolean);

            const table = document.createElement("table");
            table.className = "w-full text-xs";
            const thead = document.createElement("thead");
            const headRow = document.createElement("tr");
            (artifact.columns || []).forEach((col) => {
                const th = document.createElement("th");
                th.className = "text-left font-mono text-[9px] uppercase tracking-widest text-on-surface-muted border-b border-border-hairline pb-2 pr-4";
                th.textContent = col;
                headRow.appendChild(th);
            });
            if (hasLinks) {
                const th = document.createElement("th");
                th.className = "border-b border-border-hairline pb-2";
                headRow.appendChild(th);
            }
            thead.appendChild(headRow);
            table.appendChild(thead);
            const tbody = document.createElement("tbody");
            (artifact.rows || []).forEach((row, i) => {
                const tr = document.createElement("tr");
                row.forEach((cell) => {
                    const td = document.createElement("td");
                    td.className = "font-medium text-on-surface border-b border-border-hairline/60 py-2 pr-4";
                    td.textContent = cell;
                    tr.appendChild(td);
                });
                if (hasLinks) {
                    const td = document.createElement("td");
                    td.className = "border-b border-border-hairline/60 py-2 text-right";
                    const url = rowUrls[i];
                    if (url) {
                        const a = document.createElement("a");
                        a.href = url;
                        a.target = "_blank";
                        a.rel = "noopener noreferrer";
                        a.title = "View in Xero";
                        a.className = "inline-flex text-on-surface-muted hover:text-secondary transition-colors";
                        const icon = document.createElement("i");
                        icon.setAttribute("data-lucide", "external-link");
                        icon.className = "w-3.5 h-3.5";
                        a.appendChild(icon);
                        td.appendChild(a);
                    }
                    tr.appendChild(td);
                }
                tbody.appendChild(tr);
            });
            table.appendChild(tbody);
            container.appendChild(table);
        } else {
            const canvasEl = document.createElement("canvas");
            container.appendChild(canvasEl);
            const points = artifact.points || [];
            if (chartRef.chart) { chartRef.chart.destroy(); chartRef.chart = null; }
            chartRef.chart = new Chart(canvasEl.getContext("2d"), {
                type: artifact.kind === "pie" ? "pie" : artifact.kind,
                data: {
                    labels: points.map((p) => p.label),
                    datasets: [{
                        label: artifact.title || "",
                        data: points.map((p) => p.value),
                        backgroundColor: ["#C5F26E", "#2C4A3E", "#B6E254", "#5A6A60", "#DDD7C6", "#3B7A4A"],
                        borderColor: "#1B342B",
                        borderWidth: artifact.kind === "line" ? 2 : 1,
                    }],
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: artifact.kind === "pie" } },
                },
            });
        }

        if (artifact.insight) {
            const caption = document.createElement("p");
            caption.className = "mt-4 text-xs text-on-surface-muted font-medium leading-relaxed";
            caption.textContent = artifact.insight;
            container.appendChild(caption);
        }
        refreshIcons();
    }

    const addArtifactToCanvas = (artifact) => {
        if (canvasEmptyState) canvasEmptyState.remove();
        artifactHistory.push(artifact);
        renderArtifactInto(canvasBody, artifact, canvasChartRef, true);

        canvasHistory.classList.remove("hidden");
        canvasHistory.classList.add("flex");
        const pill = document.createElement("button");
        pill.type = "button";
        pill.className = "px-3 py-1.5 rounded-full font-mono text-[9px] uppercase tracking-widest bg-neutral border border-border-hairline text-secondary hover:bg-primary/20 transition-colors";
        pill.textContent = artifact.title || `Artefact ${artifactHistory.length}`;
        pill.addEventListener("click", () => renderArtifactInto(canvasBody, artifact, canvasChartRef, true));
        canvasHistory.appendChild(pill);
    };

    const addInlineArtifactCard = (parentBubble, artifact) => {
        const card = document.createElement("div");
        card.className = "relative mt-3 bg-surface border border-border-hairline rounded-md p-4";
        renderArtifactInto(card, artifact, { chart: null }, true);
        parentBubble.appendChild(card);
    };

    const appendMessage = (role, content, artifact, toolLog) => {
        hideEmptyState();
        const b = bubble(role, content);
        if (artifact) addInlineArtifactCard(b, artifact);
        if (role === "assistant") {
            const details = toolLogDetails(toolLog);
            if (details) b.appendChild(details);
        }
        messagesCont.appendChild(b);
        messagesCont.scrollTop = messagesCont.scrollHeight;
        refreshIcons();
        return b;
    };

    const typingIndicator = () => {
        const wrap = document.createElement("div");
        wrap.className = "self-start max-w-[80%] bg-neutral border border-border-hairline rounded-lg px-5 py-3.5";
        const p = document.createElement("p");
        p.className = "text-sm font-medium text-on-surface-muted font-mono uppercase text-[10px] tracking-widest animate-pulse";
        p.textContent = "Thinking…";
        wrap.appendChild(p);
        messagesCont.appendChild(wrap);
        messagesCont.scrollTop = messagesCont.scrollHeight;
        return wrap;
    };

    const addMemoryFact = (fact) => {
        if (memoryEmptyState) memoryEmptyState.remove();
        const row = document.createElement("div");
        row.className = "flex items-start justify-between gap-3 py-2 border-b border-border-hairline/60 last:border-0";
        const p = document.createElement("p");
        p.className = "text-xs font-medium text-on-surface leading-relaxed flex-1";
        p.textContent = fact.content;
        row.appendChild(p);

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.title = "Forget this";
        delBtn.className = "text-on-surface-muted hover:text-error transition-colors shrink-0";
        const icon = document.createElement("i");
        icon.setAttribute("data-lucide", "trash-2");
        icon.className = "w-3.5 h-3.5";
        delBtn.appendChild(icon);
        delBtn.addEventListener("click", async () => {
            row.remove();
            try {
                await fetch(`/api/chat/${tenantId}/memory/${fact.id}`, {
                    method: "DELETE",
                    headers: { "X-CSRFToken": CHAT_CONFIG.csrfToken },
                });
            } catch (err) {
                console.error("Failed to delete memory fact", err);
            }
        });
        row.appendChild(delBtn);
        memoryBody.appendChild(row);
        refreshIcons();
    };

    // Hydrate previous conversation for this tenant/session
    const historyUrl = currentSessionId
        ? `/api/chat/${tenantId}/history?session_id=${currentSessionId}`
        : `/api/chat/${tenantId}/history`;
    fetch(historyUrl)
        .then((res) => res.json())
        .then((data) => {
            if (data.status !== "Success") return;
            setSessionId(data.session_id);
            if (!data.messages || data.messages.length === 0) return;
            data.messages.forEach((m) => {
                appendMessage(m.role, m.content, m.artifact, null);
                if (m.artifact) addArtifactToCanvas(m.artifact);
            });
        })
        .catch((err) => console.error("Chat history load failed", err));

    // Client memory panel
    fetch(`/api/chat/${tenantId}/memory`)
        .then((res) => res.json())
        .then((data) => {
            if (data.status === "Success" && data.facts) {
                data.facts.slice().reverse().forEach(addMemoryFact);
            }
        })
        .catch((err) => console.error("Memory load failed", err));

    if (memoryForm) {
        memoryForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const content = memoryInput.value.trim();
            if (!content) return;
            memoryInput.disabled = true;
            try {
                const res = await fetch(`/api/chat/${tenantId}/memory`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "X-CSRFToken": CHAT_CONFIG.csrfToken },
                    body: JSON.stringify({ content }),
                });
                const data = await res.json();
                if (data.status === "Success") {
                    addMemoryFact(data.fact);
                    memoryInput.value = "";
                }
            } catch (err) {
                console.error("Failed to add memory fact", err);
            } finally {
                memoryInput.disabled = false;
                memoryInput.focus();
            }
        });
    }

    if (tenantSelect) {
        tenantSelect.addEventListener("change", (e) => {
            window.location.href = `/chat?tenant_id=${encodeURIComponent(e.target.value)}`;
        });
    }

    if (newChatBtn) {
        newChatBtn.addEventListener("click", async () => {
            newChatBtn.disabled = true;
            try {
                const res = await fetch(`/api/chat/${tenantId}/new`, {
                    method: "POST",
                    headers: { "X-CSRFToken": CHAT_CONFIG.csrfToken },
                });
                const data = await res.json();
                if (data.status === "Success") {
                    // Navigate with the new session's real id — a bare
                    // /chat?tenant_id=... with no session_id falls back to
                    // the most recently updated session (so a plain reload
                    // resumes where you left off), which is exactly what
                    // silently reopened the old conversation before.
                    window.location.href = `/chat?tenant_id=${encodeURIComponent(tenantId)}&session_id=${data.session_id}`;
                } else {
                    newChatBtn.disabled = false;
                }
            } catch (err) {
                newChatBtn.disabled = false;
            }
        });
    }

    const loadSessionsList = async () => {
        historyPanel.innerHTML = '<p class="p-3 font-mono text-[10px] uppercase tracking-widest text-on-surface-muted">Loading…</p>';
        try {
            const res = await fetch(`/api/chat/${tenantId}/sessions`);
            const data = await res.json();
            historyPanel.innerHTML = "";
            if (data.status !== "Success" || !data.sessions || data.sessions.length === 0) {
                historyPanel.innerHTML = '<p class="p-3 text-xs text-on-surface-muted font-medium">No previous conversations yet.</p>';
                return;
            }
            data.sessions.forEach((s) => {
                const item = document.createElement("a");
                item.href = `/chat?tenant_id=${encodeURIComponent(tenantId)}&session_id=${s.id}`;
                item.className = "block px-4 py-3 rounded-md hover:bg-neutral transition-colors"
                    + (s.id === currentSessionId ? " bg-primary/10" : "");
                const preview = document.createElement("p");
                preview.className = "text-xs font-bold text-on-surface truncate";
                preview.textContent = s.preview;
                const meta = document.createElement("p");
                meta.className = "font-mono text-[9px] uppercase tracking-widest text-on-surface-muted mt-1";
                meta.textContent = `${s.message_count} message${s.message_count === 1 ? "" : "s"}`;
                item.appendChild(preview);
                item.appendChild(meta);
                historyPanel.appendChild(item);
            });
        } catch (err) {
            historyPanel.innerHTML = '<p class="p-3 text-xs text-error font-medium">Failed to load history.</p>';
        }
    };

    if (historyBtn) {
        historyBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            const isHidden = historyPanel.classList.contains("hidden");
            historyPanel.classList.toggle("hidden");
            if (isHidden) loadSessionsList();
        });
        document.addEventListener("click", (e) => {
            if (!historyPanel.classList.contains("hidden") && !historyPanel.contains(e.target) && e.target !== historyBtn) {
                historyPanel.classList.add("hidden");
            }
        });
    }

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;

        appendMessage("user", text, null, null);
        input.value = "";
        input.style.height = "auto";
        sendBtn.disabled = true;
        input.disabled = true;
        const typing = typingIndicator();

        try {
            const res = await fetch(`/api/chat/${tenantId}/message`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": CHAT_CONFIG.csrfToken },
                body: JSON.stringify({ message: text, session_id: currentSessionId }),
            });
            const data = await res.json();
            typing.remove();

            if (data.status === "Success") {
                setSessionId(data.session_id);
                appendMessage("assistant", data.reply, data.artifact, data.tool_log);
                if (data.artifact) addArtifactToCanvas(data.artifact);
                (data.remembered_facts || []).forEach(addMemoryFact);
            } else {
                appendMessage("assistant", `Sorry — ${data.message || "something went wrong."}`, null, null);
            }
        } catch (err) {
            typing.remove();
            appendMessage("assistant", "Sorry — a network error stopped that request.", null, null);
        } finally {
            sendBtn.disabled = false;
            input.disabled = false;
            input.focus();
        }
    });

    // Auto-grow the textarea and let Enter (without Shift) send.
    input.addEventListener("input", () => {
        input.style.height = "auto";
        input.style.height = `${Math.min(input.scrollHeight, 128)}px`;
    });
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            form.requestSubmit();
        }
    });
});
