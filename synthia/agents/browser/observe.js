(() => {
  const SELECTOR = [
    "a[href]", "button", "input:not([type=hidden])", "select", "textarea", "summary",
    "[role=button]", "[role=link]", "[role=tab]", "[role=menuitem]", "[role=option]",
    "[role=checkbox]", "[role=radio]", "[role=switch]", "[role=combobox]", "[role=textbox]",
    "[contenteditable=true]", "[onclick]",
  ].join(",");
  const MODAL = "[role=dialog], dialog[open], [aria-modal=true]";
  const vw = window.innerWidth, vh = window.innerHeight;
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const visible = (el) => {
    const st = getComputedStyle(el);
    if (st.display === "none" || st.visibility === "hidden" || st.opacity === "0") return false;
    if (el.getAttribute("aria-hidden") === "true") return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1 && r.bottom > -vh && r.top < vh * 3;
  };
  const nameOf = (el) => {
    const aria = el.getAttribute("aria-label");
    if (aria) return clean(aria);
    const labelled = el.getAttribute("aria-labelledby");
    if (labelled) {
      const t = labelled.split(/\s+/).map((id) => document.getElementById(id)?.textContent || "").join(" ");
      if (clean(t)) return clean(t);
    }
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT") {
      const lbl = el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : el.closest("label");
      const t = clean(lbl?.textContent) || clean(el.placeholder) || clean(el.getAttribute("title")) || clean(el.name);
      if (el.tagName === "INPUT" && ["submit", "button"].includes(el.type)) return clean(el.value) || t;
      return t;
    }
    const img = el.querySelector("img[alt]");
    return clean(el.innerText || el.textContent) || clean(img?.alt) || clean(el.getAttribute("title"));
  };
  const kindOf = (el) => {
    const role = el.getAttribute("role");
    if (el.tagName === "A") return "link";
    if (el.tagName === "BUTTON" || role === "button") return "button";
    if (el.tagName === "SELECT") return "select";
    if (el.tagName === "TEXTAREA" || el.getAttribute("contenteditable") === "true" || role === "textbox") return "textbox";
    if (el.tagName === "INPUT") {
      const t = (el.type || "text").toLowerCase();
      if (["submit", "button", "image", "reset"].includes(t)) return "button";
      if (["checkbox", "radio"].includes(t)) return t;
      return t === "text" ? "textbox" : t;
    }
    return role || el.tagName.toLowerCase();
  };
  const extraOf = (el, kind) => {
    const bits = [];
    if (kind === "link") {
      try {
        const u = new URL(el.href);
        if (u.hostname !== location.hostname) bits.push(`-> ${u.hostname}`);
        else if (u.pathname && u.pathname !== "/" && u.pathname !== location.pathname) bits.push(`-> ${u.pathname.slice(0, 40)}`);
      } catch (_) {}
    }
    if (kind === "textbox" || kind === "search" || kind === "email" || kind === "password" || kind === "number") {
      if (el.value) bits.push(`value='${clean(el.value).slice(0, 30)}'`);
    }
    if (kind === "select") {
      const opts = Array.from(el.options || []).slice(0, 8).map((o) => clean(o.textContent)).filter(Boolean);
      if (opts.length) bits.push(`options=[${opts.join(", ")}]`);
      if (el.value) bits.push(`selected='${clean(el.selectedOptions?.[0]?.textContent).slice(0, 30)}'`);
    }
    if (kind === "checkbox" || kind === "radio") bits.push(el.checked ? "checked" : "unchecked");
    if (el.disabled) bits.push("disabled");
    return bits.join(" ");
  };
  document.querySelectorAll("[data-synthia-ref]").forEach((el) => el.removeAttribute("data-synthia-ref"));
  const seen = new Set();
  const elements = [];
  let ref = 0;
  for (const el of document.querySelectorAll(SELECTOR)) {
    if (seen.has(el) || !visible(el)) continue;
    seen.add(el);
    const r = el.getBoundingClientRect();
    const kind = kindOf(el);
    const name = nameOf(el);
    if (!name && kind === "link") continue;
    ref += 1;
    el.setAttribute("data-synthia-ref", String(ref));
    elements.push({
      ref, kind, name: name.slice(0, 120), extra: extraOf(el, kind),
      inViewport: r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw,
      modal: !!el.closest(MODAL),
    });
    if (elements.length >= 400) break;
  }
  const alerts = Array.from(document.querySelectorAll("[role=alert], [role=status], [role=dialog], dialog[open], [aria-modal=true]"))
    .filter(visible).map((el) => clean(el.innerText).slice(0, 300)).filter(Boolean).slice(0, 5);
  const main = document.querySelector("main, article, [role=main]") || document.body;
  const BLOCK = /^(P|DIV|SECTION|ARTICLE|HEADER|FOOTER|NAV|UL|OL|TABLE|TR|FORM|LI|H[1-6]|DD|DT|BLOCKQUOTE|PRE|LABEL|BUTTON|TD|TH)$/;
  const lines = [];
  const walk = (node, depth) => {
    if (node.nodeType === Node.TEXT_NODE) {
      const t = clean(node.textContent);
      if (t) lines.push(t);
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    if (["SCRIPT", "STYLE", "NOSCRIPT", "SVG", "TEMPLATE"].includes(node.tagName)) return;
    if (node.hasAttribute("hidden") || node.getAttribute("aria-hidden") === "true") return;
    const st = getComputedStyle(node);
    if (st.display === "none" || st.visibility === "hidden") return;
    const tag = node.tagName;
    if (/^H[1-6]$/.test(tag)) lines.push("\n" + "#".repeat(Number(tag[1])) + " " + clean(node.innerText) + "\n");
    else if (tag === "LI") lines.push("\n- " + clean(node.innerText) + "\n");
    else if (tag === "TR") lines.push("\n| " + Array.from(node.cells || []).map((c) => clean(c.innerText)).join(" | ") + " |\n");
    else {
      if (BLOCK.test(tag)) lines.push("\n");
      for (const child of node.childNodes) walk(child, depth + 1);
      if (BLOCK.test(tag)) lines.push("\n");
    }
    if (lines.length > 4000) throw new Error("__stop__");
  };
  try { walk(main, 0); } catch (e) { if (!String(e.message).includes("__stop__")) throw e; }
  const text = lines.join(" ").replace(/[ \t]+/g, " ").replace(/\s*\n\s*/g, "\n").replace(/\n{2,}/g, "\n").trim().slice(0, 5000);
  return {
    url: location.href, title: document.title, text, alerts, elements,
    scroll: { y: Math.round(window.scrollY), height: Math.round(document.documentElement.scrollHeight), viewport: vh },
  };
})()
