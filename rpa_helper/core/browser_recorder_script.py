"""注入到浏览器页面里的录制脚本。

由 browser_recorder.py 通过 Playwright add_init_script 注入到每个页面。
脚本监听用户的点击、输入、跳转等动作，通过 window.__rpaRecord(...)
把事件回传到 Python 侧。

选择器生成策略（最优 → 兜底）：
  1. data-testid 属性
  2. aria-label
  3. role + 可访问名
  4. 可见文本（短文本优先）
  5. id 属性
  6. 带 class 的 CSS 路径（最多 3 层）

脚本以 bubble 阶段捕获事件，从不调用 preventDefault，避免影响页面
本身的行为。

Author: huaiqing.wang
"""

from __future__ import annotations


# Pure JavaScript, returned as a string. Indented for readability.
RECORDER_SCRIPT = r"""
(() => {
    if (window.__rpaRecorderInstalled) return;
    window.__rpaRecorderInstalled = true;

    const MAX_TEXT = 80;

    function isVisible(el) {
        if (!el || !(el instanceof Element)) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    }

    function trim(text) {
        if (!text) return "";
        const t = text.replace(/\s+/g, " ").trim();
        return t.length > MAX_TEXT ? t.slice(0, MAX_TEXT) : t;
    }

    function cssEscape(s) {
        if (window.CSS && CSS.escape) return CSS.escape(s);
        return s.replace(/(["\\#.:>\\[\\]])/g, "\\\\$1");
    }

    function escapeAttr(s) {
        return String(s).replace(/"/g, '\\"');
    }

    function selectorCandidates(el) {
        const candidates = [];
        if (!el || !(el instanceof Element)) return candidates;

        // 1. data-testid
        const tid = el.getAttribute("data-testid")
                 || el.getAttribute("data-test-id")
                 || el.getAttribute("data-test");
        if (tid) candidates.push(`[data-testid="${escapeAttr(tid)}"]`);

        // 2. aria-label
        const aria = el.getAttribute("aria-label");
        if (aria && aria.length < 60) {
            candidates.push(`[aria-label="${escapeAttr(aria)}"]`);
        }

        // 3. id (only stable-looking ones — no random hashes)
        const id = el.id;
        if (id && id.length < 40 && !/^[0-9]/.test(id)
            && !/(uuid|random|tmp|gen\\d+)/i.test(id)) {
            candidates.push(`#${cssEscape(id)}`);
        }

        // 3b. name attribute (very common on form inputs)
        const tagLower = el.tagName.toLowerCase();
        const nameAttr = el.getAttribute("name");
        if (nameAttr && nameAttr.length < 40
            && (tagLower === "input" || tagLower === "textarea" || tagLower === "select")) {
            candidates.push(`${tagLower}[name="${escapeAttr(nameAttr)}"]`);
        }

        // 3c. input[type=submit] is a strong, stable hint on its own.
        if (tagLower === "input") {
            const itype = (el.getAttribute("type") || "").toLowerCase();
            if (itype === "submit" || itype === "button" || itype === "reset") {
                candidates.push(`input[type="${itype}"]`);
            }
        }

        // 4. role + accessible name — only if the name is short and looks
        //    like a real label (not a paragraph of marketing copy).
        const role = el.getAttribute("role") || implicitRole(el);
        const name = accessibleName(el);
        if (role && name && isCleanLabel(name)) {
            candidates.push(`role=${role}[name="${escapeAttr(name)}"]`);
        }

        // 5. visible text — Playwright's text="..." matches exact normalized
        //    text. We only emit it when it's likely to be the element's own
        //    label, not a span of unrelated UI chunks.
        if (name && isCleanLabel(name) && tagLower !== "input" && tagLower !== "textarea") {
            candidates.push(`text="${escapeAttr(name)}"`);
        }

        // 6. CSS path (last resort)
        candidates.push(cssPath(el));

        return candidates.filter(Boolean);
    }

    // True for labels that are likely to be the element's own caption,
    // false for things like "👈 复杂问题文心助手回答更优 百度一下" where the
    // element actually contains a tooltip + sibling button concatenated.
    function isCleanLabel(text) {
        if (!text) return false;
        if (text.length > 30) return false;
        // Reject text containing pictographic / emoji characters — they
        // almost always come from marketing badges glued onto a real button.
        // \p{Extended_Pictographic} covers most emojis; fall back if the
        // engine lacks Unicode property escapes.
        try {
            if (/\p{Extended_Pictographic}/u.test(text)) return false;
        } catch (_) {
            // Older engines: catch common emoji ranges manually.
            if (/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(text)) return false;
        }
        return true;
    }

    function implicitRole(el) {
        const tag = el.tagName.toLowerCase();
        if (tag === "button") return "button";
        if (tag === "a" && el.hasAttribute("href")) return "link";
        if (tag === "input") {
            const type = (el.type || "text").toLowerCase();
            if (type === "button" || type === "submit") return "button";
            if (type === "checkbox") return "checkbox";
            if (type === "radio") return "radio";
            return "textbox";
        }
        if (tag === "textarea") return "textbox";
        if (tag === "select") return "combobox";
        return "";
    }

    function accessibleName(el) {
        const aria = el.getAttribute("aria-label");
        if (aria) return trim(aria);
        if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
            if (el.placeholder) return trim(el.placeholder);
            if (el.name) return trim(el.name);
            // associated <label>
            if (el.id) {
                const lbl = document.querySelector(`label[for="${cssEscape(el.id)}"]`);
                if (lbl) return trim(lbl.textContent);
            }
            return "";
        }
        return trim(el.textContent);
    }

    function cssPath(el) {
        const parts = [];
        let cur = el;
        let depth = 0;
        while (cur && cur.nodeType === 1 && depth < 4) {
            let part = cur.tagName.toLowerCase();
            if (cur.id && cur.id.length < 40) {
                parts.unshift(`${part}#${cssEscape(cur.id)}`);
                break;
            }
            const cls = Array.from(cur.classList || [])
                .filter(c => c && !/^(\\d|js-|is-|has-)/.test(c) && c.length < 30)
                .slice(0, 2);
            if (cls.length > 0) part += "." + cls.map(cssEscape).join(".");
            // nth-of-type for disambiguation
            const parent = cur.parentElement;
            if (parent) {
                const siblings = Array.from(parent.children)
                    .filter(c => c.tagName === cur.tagName);
                if (siblings.length > 1) {
                    const idx = siblings.indexOf(cur) + 1;
                    part += `:nth-of-type(${idx})`;
                }
            }
            parts.unshift(part);
            cur = cur.parentElement;
            depth += 1;
        }
        return parts.join(" > ");
    }

    function record(kind, el, extra) {
        try {
            const candidates = selectorCandidates(el);
            const name = accessibleName(el);
            const payload = JSON.stringify({
                kind,
                candidates,
                name: name || "",
                tag: el ? el.tagName.toLowerCase() : "",
                value: extra && extra.value !== undefined ? extra.value : "",
                url: location.href,
                ts: Date.now(),
            });
            if (window.__rpaRecord) {
                window.__rpaRecord(payload);
            }
            flashElement(el, "rgba(80, 200, 120, 0.85)");
        } catch (err) {
            console.warn("RPA recorder error:", err);
        }
    }

    // --- Highlight overlay ---------------------------------------------
    // A single absolutely-positioned <div> we move around to outline the
    // element currently under mouse, or the element matched by a selector
    // when test-running a step from Python. We never preventDefault.

    const HIGHLIGHT_ID = "__rpa_recorder_highlight__";

    function ensureHighlight() {
        let box = document.getElementById(HIGHLIGHT_ID);
        if (box) return box;
        box = document.createElement("div");
        box.id = HIGHLIGHT_ID;
        box.style.cssText = [
            "position:fixed",
            "pointer-events:none",
            "z-index:2147483646",
            "border:2px solid #4f8cff",
            "background:rgba(79,140,255,0.12)",
            "border-radius:3px",
            "transition:all 80ms ease-out",
            "display:none",
            "box-shadow:0 0 0 1px rgba(0,0,0,0.15)",
        ].join(";");
        // Append to <html> so it works even before <body> exists.
        (document.body || document.documentElement).appendChild(box);
        return box;
    }

    function positionHighlight(el, color) {
        if (!el || !(el instanceof Element)) return false;
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return false;
        const box = ensureHighlight();
        box.style.left = Math.max(0, r.left - 2) + "px";
        box.style.top = Math.max(0, r.top - 2) + "px";
        box.style.width = r.width + 4 + "px";
        box.style.height = r.height + 4 + "px";
        if (color) box.style.borderColor = color;
        box.style.display = "block";
        return true;
    }

    function hideHighlight() {
        const box = document.getElementById(HIGHLIGHT_ID);
        if (box) box.style.display = "none";
    }

    function flashElement(el, color) {
        if (!positionHighlight(el, color || "#50c878")) return;
        clearTimeout(window.__rpa_flash_timer);
        window.__rpa_flash_timer = setTimeout(() => {
            // Restore to hover color or hide.
            if (window.__rpa_hover_el && document.contains(window.__rpa_hover_el)) {
                positionHighlight(window.__rpa_hover_el, "#4f8cff");
            } else {
                hideHighlight();
            }
        }, 600);
    }

    // Track the element under the mouse and outline it.
    document.addEventListener("mousemove", (e) => {
        const el = e.target;
        if (!el || !(el instanceof Element)) return;
        // Match the click handler's target picker so the outline reflects
        // what would actually get recorded.
        const target = pickClickTarget(el);
        window.__rpa_hover_el = target;
        positionHighlight(target, "#4f8cff");
    }, true);

    document.addEventListener("mouseleave", () => {
        window.__rpa_hover_el = null;
        hideHighlight();
    }, true);

    // Exposed to Python: locate by selector and flash (used by "test step").
    // Returns a small object describing what happened so the caller can show
    // a friendly result without doing another round-trip.
    window.__rpaHighlightSelector = (selector) => {
        try {
            const el = document.querySelector(selector);
            if (!el) {
                hideHighlight();
                return { ok: false, reason: "not_found", count: 0 };
            }
            const count = document.querySelectorAll(selector).length;
            const ok = positionHighlight(el, "#ffae42");
            // Hold the highlight for 1.2s so the user can see it.
            clearTimeout(window.__rpa_flash_timer);
            window.__rpa_flash_timer = setTimeout(() => {
                if (window.__rpa_hover_el && document.contains(window.__rpa_hover_el)) {
                    positionHighlight(window.__rpa_hover_el, "#4f8cff");
                } else {
                    hideHighlight();
                }
            }, 1200);
            return { ok, count };
        } catch (err) {
            return { ok: false, reason: "invalid_selector", error: String(err) };
        }
    };

    // Click handler — capture phase so we get it even if page stops propagation.
    document.addEventListener("click", (e) => {
        if (!isVisible(e.target)) return;
        const el = pickClickTarget(e.target);
        record("click", el, {});
    }, true);

    // Decide which element the user really "meant" to click.
    //
    // Rules:
    //   1. If the original target is itself interactive (input/button/a/select/
    //      textarea/role=button), use it. Don't climb — climbing a submit
    //      <input> wraps it in some marketing div whose visible text spans
    //      multiple unrelated chunks.
    //   2. Otherwise walk up at most 3 levels looking for the closest
    //      interactive ancestor. Stop at the first one found.
    //   3. If nothing interactive is found, return the original element.
    function pickClickTarget(start) {
        if (!start || !(start instanceof Element)) return start;
        if (isInteractive(start)) return start;
        let cur = start.parentElement;
        let hops = 0;
        while (cur && hops < 3) {
            if (isInteractive(cur)) return cur;
            cur = cur.parentElement;
            hops += 1;
        }
        return start;
    }

    function isInteractive(el) {
        if (!el || !(el instanceof Element)) return false;
        const tag = el.tagName.toLowerCase();
        if (tag === "button" || tag === "a" || tag === "input"
            || tag === "select" || tag === "textarea" || tag === "label") {
            return true;
        }
        const role = (el.getAttribute("role") || "").toLowerCase();
        if (role === "button" || role === "link" || role === "checkbox"
            || role === "radio" || role === "menuitem" || role === "tab") {
            return true;
        }
        // onclick / tabindex >= 0 → user clearly made it clickable.
        if (el.hasAttribute("onclick")) return true;
        const ti = el.getAttribute("tabindex");
        if (ti !== null && ti !== "" && parseInt(ti, 10) >= 0) return true;
        return false;
    }

    // Input change handler — debounced so we capture final value, not each keystroke.
    const inputTimers = new WeakMap();
    document.addEventListener("input", (e) => {
        const el = e.target;
        if (!el || (el.tagName !== "INPUT" && el.tagName !== "TEXTAREA")) return;
        if (inputTimers.has(el)) clearTimeout(inputTimers.get(el));
        const t = setTimeout(() => {
            record("input", el, { value: el.value || "" });
            inputTimers.delete(el);
        }, 600);
        inputTimers.set(el, t);
    }, true);

    // Submit handler — captures Enter inside forms.
    document.addEventListener("submit", (e) => {
        record("submit", e.target, {});
    }, true);

    // Navigation observer — record url changes (SPA pushState etc).
    let lastUrl = location.href;
    const reportNav = () => {
        if (location.href !== lastUrl) {
            lastUrl = location.href;
            try {
                if (window.__rpaRecord) {
                    window.__rpaRecord(JSON.stringify({
                        kind: "navigate",
                        candidates: [],
                        name: "",
                        tag: "",
                        value: location.href,
                        url: location.href,
                        ts: Date.now(),
                    }));
                }
            } catch (_) {}
        }
    };
    setInterval(reportNav, 500);
})();
"""


def best_selector(candidates: list[str]) -> str:
    """Pick the most stable selector from a list, falling back to last."""
    if not candidates:
        return ""
    return candidates[0]
