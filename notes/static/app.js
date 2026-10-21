/*
  Forget-Me-Note's JavaScript. Every page works without it (forms post and
  the server answers with a page). This file makes things smoother:

  - the editor saves as you type, with a calm status and retries on failure
  - suggestions for [[links]], #tags and the tag box, while typing
  - a live preview, focus mode, and copy buttons
  - checkboxes on cards tick without a reload (with a little party at 100%)
  - select mode for doing things to many notes at once
  - the welcome tour, keyboard shortcuts, snackbars and sheets that behave

  Requests sent with fetch() carry "X-Requested-With: fetch", so the server
  answers with a little JSON instead of a whole page (see is_fetch()).
*/
"use strict";

const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const phone = window.matchMedia("(max-width: 900px)");

/** POST a FormData (or a plain object) with fetch(), with the CSRF token added. */
function post(url, data) {
  const body = data instanceof FormData ? data : new FormData();
  if (!(data instanceof FormData)) {
    for (const [key, value] of Object.entries(data || {})) body.append(key, value);
  }
  if (!body.has("csrf_token")) body.append("csrf_token", csrfToken);
  return fetch(url, { method: "POST", body, headers: { "X-Requested-With": "fetch" } });
}

/** Wait until `wait` ms have passed without another call, then run fn once. */
function debounce(fn, wait) {
  let timer;
  const debounced = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), typeof wait === "function" ? wait() : wait);
  };
  debounced.cancel = () => clearTimeout(timer);
  return debounced;
}

/** True while the person is typing in a box, so single-key shortcuts stay out of the way. */
function isTyping(target) {
  return target.closest("input, textarea, select, [contenteditable]") !== null;
}

/** The popover that's open right now, if any. (:popover-open is new, so be careful.) */
function openSheet() {
  try { return document.querySelector(".sheet:popover-open"); } catch { return null; }
}

/** "just now", "2 min ago", "1 h ago": for the save status. */
function sinceText(time) {
  const seconds = (Date.now() - time) / 1000;
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  return `${Math.round(seconds / 3600)} h ago`;
}

// ---------- Toasts and snackbars ----------

/**
 * Make a toast leave after `delay` ms. The clock stops while the mouse is
 * on it or a button in it has focus, so nobody loses an Undo mid-reach.
 */
function autoDismiss(item, delay) {
  let timer;
  const leave = () => {
    item.classList.add("is-leaving");
    setTimeout(() => item.remove(), 300);
  };
  const start = () => { clearTimeout(timer); timer = setTimeout(leave, delay); };
  const stop = () => clearTimeout(timer);
  item.addEventListener("mouseenter", stop);
  item.addEventListener("mouseleave", start);
  item.addEventListener("focusin", stop);
  item.addEventListener("focusout", start);
  item.querySelector("[data-dismiss]")?.addEventListener("click", leave);
  start();
}

/** Show a short message at the bottom, like the server's flash() toasts. */
function toast(message, isError = false) {
  const item = document.createElement("p");
  item.className = "toast" + (isError ? " toast-error" : "");
  item.setAttribute("role", isError ? "alert" : "status");
  item.textContent = message;
  document.querySelector(".toasts").append(item);
  autoDismiss(item, isError ? 8000 : 3500);
}

// Messages from the server: Undo snackbars stay 10 s, errors 8 s, the rest 4 s.
document.querySelectorAll(".toasts .toast").forEach((item) => {
  const delay = item.classList.contains("toast-snackbar") ? 10000 : item.classList.contains("toast-error") ? 8000 : 4000;
  autoDismiss(item, delay);
});

// <form data-confirm="Delete this?"> asks first. Only used for things that
// can't be undone: normal deletes have Undo instead.
document.addEventListener("submit", (event) => {
  const question = event.target.dataset.confirm;
  if (question && !window.confirm(question)) event.preventDefault();
});

// ---------- A little celebration ----------

/** Petals fly out from an element (skipped for people who prefer less motion). */
function celebrate(element) {
  if (!element) return;
  element.classList.remove("celebrate");
  void element.offsetWidth; // restart the animation if it ran before
  element.classList.add("celebrate");
  if (reducedMotion.matches) return;
  const box = element.getBoundingClientRect();
  const burst = document.createElement("div");
  burst.className = "confetti";
  burst.style.left = `${box.left + box.width / 2}px`;
  burst.style.top = `${box.top + box.height / 2}px`;
  const colors = ["#9dbcff", "#ffc53d", "#7b61e8", "#2f9e57", "#f2711c"];
  for (let i = 0; i < 14; i++) {
    const petal = document.createElement("span");
    const angle = (Math.PI * 2 * i) / 14;
    petal.style.background = colors[i % colors.length];
    petal.style.setProperty("--x", `${Math.cos(angle) * (40 + Math.random() * 40)}px`);
    petal.style.setProperty("--y", `${Math.sin(angle) * (40 + Math.random() * 40) - 20}px`);
    burst.append(petal);
  }
  document.body.append(burst);
  setTimeout(() => burst.remove(), 1000);
}

// ---------- Sheets (popovers) ----------

document.querySelectorAll(".sheet[popover]").forEach((sheet) => {
  // Opening a sheet moves focus into it; closing it, back where it was.
  let opener = null;
  sheet.addEventListener("toggle", (event) => {
    if (event.newState === "open") {
      opener = document.activeElement;
      const first = sheet.querySelector("input:not([type=hidden]), button:not([hidden]), a[href], textarea, select");
      first?.focus({ preventScroll: true });
    } else if (opener && document.contains(opener)) {
      opener.focus({ preventScroll: true });
    }
  });

  // On a phone, drag a sheet down to close it.
  let startY = null;
  let dragged = 0;
  sheet.addEventListener("touchstart", (event) => {
    if (!phone.matches || sheet.scrollTop > 0) return;
    startY = event.touches[0].clientY;
    dragged = 0;
    sheet.classList.add("is-dragging");
  }, { passive: true });
  sheet.addEventListener("touchmove", (event) => {
    if (startY === null) return;
    dragged = Math.max(0, event.touches[0].clientY - startY);
    sheet.style.transform = `translateY(${dragged}px)`;
  }, { passive: true });
  sheet.addEventListener("touchend", () => {
    if (startY === null) return;
    sheet.classList.remove("is-dragging");
    sheet.style.transform = "";
    if (dragged > 90 && sheet.getAttribute("popover") !== "manual") sheet.hidePopover();
    startY = null;
  });
});

// Keep Tab inside an open sheet, so keyboard users don't wander behind it.
document.addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const sheet = openSheet();
  if (!sheet) return;
  const focusable = [...sheet.querySelectorAll("input:not([type=hidden]), button, a[href], textarea, select, summary")]
    .filter((element) => !element.disabled && !element.hidden && element.offsetParent !== null);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  else if (!sheet.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
});

// A filter box in a sheet hides the rows that don't match (the shortcuts list).
document.querySelectorAll("[data-filter-rows]").forEach((box) => {
  box.addEventListener("input", () => {
    const words = box.value.trim().toLowerCase();
    const sheet = box.closest(".sheet");
    sheet.querySelectorAll(".shortcut-list > div").forEach((row) => {
      row.hidden = words !== "" && !row.textContent.toLowerCase().includes(words);
    });
    // Open "More shortcuts" while searching, so nothing is hidden inside it.
    const more = sheet.querySelector(".more-shortcuts");
    if (more && words) more.open = true;
  });
});

// ---------- The welcome tour ----------

const tour = document.getElementById("tour");
if (tour) {
  const slides = [...tour.querySelectorAll(".tour-slide")];
  const dots = [...tour.querySelectorAll(".tour-dots span")];
  const back = tour.querySelector("[data-tour-back]");
  const next = tour.querySelector("[data-tour-next]");
  const done = tour.querySelector("[data-tour-done]");
  let current = 0;

  const show = (index) => {
    current = index;
    slides.forEach((slide, i) => { slide.hidden = i !== index; });
    dots.forEach((dot, i) => dot.classList.toggle("is-on", i === index));
    back.hidden = index === 0;
    next.hidden = index === slides.length - 1;
    done.hidden = index !== slides.length - 1;
    (next.hidden ? done : next).focus();
  };
  next.addEventListener("click", () => show(current + 1));
  back.addEventListener("click", () => show(current - 1));

  // Finishing or skipping tells the server, then just closes: no reload.
  tour.querySelector("form").addEventListener("submit", (event) => {
    event.preventDefault();
    post(event.target.action, new FormData(event.target));
    tour.hidePopover();
  });
  tour.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight" && current < slides.length - 1) show(current + 1);
    if (event.key === "ArrowLeft" && current > 0) show(current - 1);
    if (event.key === "Escape") tour.querySelector("[data-tour-skip]").click();
  });

  if (tour.hasAttribute("data-autostart")) {
    tour.showPopover();
    show(0);
  }
}

// ---------- Keyboard shortcuts ----------

const searchBox = document.getElementById("search");
const cardLinks = () => [...document.querySelectorAll(".note-card .card-link")];

document.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  const ctrl = event.ctrlKey || event.metaKey;

  if ((ctrl && key === "k") || (key === "/" && !isTyping(event.target))) {
    event.preventDefault();
    searchBox?.focus();
    searchBox?.select();
  } else if ((key === "n" && !ctrl && !event.altKey && !isTyping(event.target)) || (event.altKey && key === "n")) {
    // Ctrl+N belongs to the browser (new window), so it's N, or Alt+N while typing.
    event.preventDefault();
    const newLink = document.querySelector(".btn-new") || document.querySelector(".bottom-new");
    if (newLink) window.location = newLink.href;
  } else if (event.key === "?" && !isTyping(event.target)) {
    document.getElementById("shortcuts")?.showPopover();
  } else if (event.key === "Escape" && event.target === searchBox && searchBox.value) {
    searchBox.value = "";
  } else if (["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"].includes(event.key)) {
    // Arrow keys move through the notes; Enter opens the one with focus.
    const links = cardLinks();
    if (!links.length || openSheet()) return;
    const forward = event.key === "ArrowDown" || event.key === "ArrowRight";
    if (event.target === searchBox && event.key === "ArrowDown") {
      event.preventDefault();
      links[0].focus();
    } else if (links.includes(event.target)) {
      event.preventDefault();
      const index = links.indexOf(event.target) + (forward ? 1 : -1);
      if (index < 0) searchBox?.focus();
      else links[Math.min(index, links.length - 1)].focus();
    }
  }
});

// ---------- Checkboxes on cards ----------

document.querySelectorAll(".note-card[data-check-url]").forEach((card) => {
  card.addEventListener("change", async (event) => {
    const box = event.target;
    if (!box.matches(".checklist input[type=checkbox]")) return;
    box.closest("li").classList.toggle("done", box.checked);
    // Move the bar right away (optimistic), and fix it if the server says no.
    const all = card.querySelectorAll(".checklist input[type=checkbox]");
    const ticked = card.querySelectorAll(".checklist input[type=checkbox]:checked");
    updateCardProgress(card, ticked.length, all.length);
    const response = await post(card.dataset.checkUrl, { line: box.dataset.line }).catch(() => null);
    if (!response || !response.ok) {
      box.checked = !box.checked;
      box.closest("li").classList.toggle("done", box.checked);
      toast("Couldn't save that tick. Check your connection and try again.", true);
      return;
    }
    const { done, total } = await response.json();
    updateCardProgress(card, done, total);
  });
});

function updateCardProgress(card, done, total) {
  const progress = card.querySelector(".progress");
  if (!progress || !total) return;
  const wasComplete = progress.classList.contains("is-complete");
  progress.querySelector(".progress-bar span").style.width = `${Math.round((done * 100) / total)}%`;
  progress.querySelector(".progress-text").textContent = `${done}/${total}`;
  progress.classList.toggle("is-complete", done === total);
  if (done === total && !wasComplete) celebrate(progress);
}
document.querySelectorAll(".note-card .progress").forEach((progress) => {
  const [done, total] = progress.querySelector(".progress-text").textContent.split("/").map(Number);
  progress.classList.toggle("is-complete", done === total);
});

// ---------- Select mode (many notes at once) ----------

const selectButton = document.querySelector("[data-select-mode]");
const bulkForm = document.getElementById("bulk-form");
if (selectButton && bulkForm) {
  selectButton.hidden = false;
  const count = bulkForm.querySelector(".bulk-count");
  const boxes = () => [...document.querySelectorAll('.card-select input[form="bulk-form"]')];
  const refresh = () => {
    const chosen = boxes().filter((box) => box.checked).length;
    count.textContent = `${chosen} selected`;
    bulkForm.querySelectorAll("button[name=action]").forEach((button) => { button.disabled = chosen === 0; });
  };
  const setSelecting = (on) => {
    document.body.classList.toggle("selecting", on);
    bulkForm.hidden = !on;
    selectButton.setAttribute("aria-pressed", String(on));
    if (!on) boxes().forEach((box) => { box.checked = false; });
    refresh();
  };
  selectButton.addEventListener("click", () => setSelecting(!document.body.classList.contains("selecting")));
  bulkForm.querySelector("[data-select-cancel]").addEventListener("click", () => setSelecting(false));
  document.addEventListener("change", (event) => { if (event.target.form === bulkForm) refresh(); });
  // In select mode, clicking a card selects it instead of opening it.
  document.addEventListener("click", (event) => {
    const link = event.target.closest(".card-link");
    if (!link || !document.body.classList.contains("selecting")) return;
    event.preventDefault();
    const box = link.closest(".note-card").querySelector(".card-select input");
    box.checked = !box.checked;
    refresh();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("selecting") && !openSheet()) setSelecting(false);
  });
}

// ---------- Quick capture on the home page ----------

const capture = document.querySelector(".capture");
if (capture) {
  const area = capture.querySelector("textarea");
  const grow = () => {
    area.style.height = "auto";
    area.style.height = `${area.scrollHeight}px`;
    // Keep the title and button showing while there's text, even when focus leaves.
    capture.classList.toggle("is-open", area.value.trim() !== "" || capture.querySelector("input[name=title]").value !== "");
  };
  capture.addEventListener("input", grow);
  area.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) capture.requestSubmit();
  });
}

// ---------- Suggestions (for [[links]], #tags and the tag box) ----------

/** How well `text` matches what was typed: 3 starts with it, 2 contains it, 1 has its letters in order. */
function fuzzyScore(typed, text) {
  const a = typed.toLowerCase();
  const b = text.toLowerCase();
  if (!a) return 1;
  if (b.startsWith(a)) return 3;
  if (b.includes(a)) return 2;
  let i = 0;
  for (const letter of b) if (letter === a[i]) i++;
  return i === a.length ? 1 : 0;
}

function fuzzyFilter(typed, options, limit = 8) {
  return options
    .map((text) => ({ text, score: fuzzyScore(typed, text) }))
    .filter((option) => option.score > 0)
    .sort((x, y) => y.score - x.score || x.text.length - y.text.length)
    .slice(0, limit)
    .map((option) => option.text);
}

/**
 * A dropdown list of suggestions. show() fills and places it, move() and
 * pick() are for the keyboard. Each item is {label, value, isNew}.
 */
let suggestCount = 0;
function createSuggest(onPick) {
  const list = document.createElement("ul");
  list.className = "suggest";
  list.id = `suggest-${++suggestCount}`;
  list.setAttribute("role", "listbox");
  list.hidden = true;
  document.body.append(list);
  let items = [];
  let active = 0;

  function draw(typed, head) {
    list.replaceChildren();
    if (head) {
      const title = document.createElement("li");
      title.className = "suggest-head";
      title.setAttribute("role", "presentation");
      title.textContent = head;
      list.append(title);
    }
    items.forEach((item, index) => {
      const option = document.createElement("li");
      option.id = `${list.id}-${index}`;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", String(index === active));
      if (item.isNew) option.className = "suggest-new";
      // Text nodes only (no innerHTML), so a note title can't become HTML.
      const at = item.isNew ? -1 : item.label.toLowerCase().indexOf(typed.toLowerCase());
      if (typed && at >= 0) {
        const mark = document.createElement("mark");
        mark.textContent = item.label.slice(at, at + typed.length);
        option.append(item.label.slice(0, at), mark, item.label.slice(at + typed.length));
      } else {
        option.textContent = item.label;
      }
      // mousedown, not click: picking mustn't take focus from the text box.
      option.addEventListener("mousedown", (event) => { event.preventDefault(); pick(index); });
      list.append(option);
    });
  }

  function show(newItems, typed, x, y, head) {
    items = newItems;
    active = 0;
    if (!items.length) return hide();
    draw(typed, head);
    list.hidden = false;
    const width = list.offsetWidth;
    list.style.left = `${Math.max(8, Math.min(x, window.scrollX + document.documentElement.clientWidth - width - 8))}px`;
    list.style.top = `${y + 4}px`;
  }
  function hide() { list.hidden = true; items = []; }
  function move(step) {
    active = (active + step + items.length) % items.length;
    list.querySelectorAll("[role=option]").forEach((option, index) => option.setAttribute("aria-selected", String(index === active)));
    list.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }
  function pick(index = active) {
    const item = items[index];
    hide();
    if (item) onPick(item);
  }
  return { show, hide, move, pick, list, get isOpen() { return !list.hidden && items.length > 0; } };
}

/** Where the text cursor is on the page, worked out with an invisible copy of the textarea. */
function caretPosition(area) {
  const mirror = document.createElement("div");
  const style = getComputedStyle(area);
  for (const property of ["boxSizing", "width", "fontFamily", "fontSize", "fontWeight", "lineHeight",
    "letterSpacing", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "tabSize"]) {
    mirror.style[property] = style[property];
  }
  Object.assign(mirror.style, { position: "absolute", visibility: "hidden", whiteSpace: "pre-wrap", overflowWrap: "break-word", top: "0", left: "0" });
  mirror.textContent = area.value.slice(0, area.selectionStart);
  const marker = document.createElement("span");
  marker.textContent = "​";
  mirror.append(marker);
  document.body.append(mirror);
  const box = area.getBoundingClientRect();
  const lineHeight = parseFloat(style.lineHeight) || 24;
  const position = {
    x: box.left + window.scrollX + marker.offsetLeft,
    y: box.top + window.scrollY + marker.offsetTop - area.scrollTop + lineHeight,
  };
  mirror.remove();
  return position;
}

// ---------- The editor ----------

const form = document.getElementById("note-form");
if (form) setUpEditor(form);

function setUpEditor(form) {
  const page = document.getElementById("editor-page");
  const body = document.getElementById("body");
  const preview = document.getElementById("preview");
  const panes = document.getElementById("panes");
  const status = document.getElementById("save-status");
  const statusText = status.querySelector(".save-text");
  const retryButton = status.querySelector(".save-retry");
  const canEdit = form.hasAttribute("data-autosave");
  const data = JSON.parse(document.getElementById("editor-data")?.textContent || "{}");

  // --- The textarea grows with its text, so the page scrolls, not the box. ---
  const grow = () => {
    body.style.height = "auto";
    body.style.height = `${body.scrollHeight + 2}px`;
  };
  body.addEventListener("input", grow);
  grow();

  // --- Write / Split / Preview, remembered for this account. ---
  const modeButtons = page.querySelectorAll("[data-mode]");
  function setMode(mode, remember = true) {
    panes.dataset.mode = mode;
    modeButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.mode === mode)));
    if (remember && canEdit) post(form.dataset.modeUrl, { mode }).catch(() => {});
    if (mode !== "write") refreshPreview();
    else if (remember) body.focus();
  }
  modeButtons.forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
  setMode(panes.dataset.mode || "write", false);

  // --- Live preview, drawn by the same Python renderer as the cards. ---
  async function refreshPreview() {
    if (panes.dataset.mode === "write") return;
    const response = await post(form.dataset.previewUrl, { body: body.value }).catch(() => null);
    if (response && response.ok) {
      const html = await response.text();
      preview.innerHTML = html.trim() ? html : '<p class="hint">Nothing to preview yet.</p>';
    }
  }
  // Long notes wait longer between previews, so typing never stutters.
  const refreshPreviewSoon = debounce(refreshPreview, () => (body.value.length > 20000 ? 900 : 250));

  // Ticking a box in the preview changes "- [ ]" to "- [x]" in the text.
  preview.addEventListener("change", (event) => {
    const box = event.target;
    if (!canEdit || !box.matches("input[type=checkbox][data-line]")) return;
    const lines = body.value.split("\n");
    const number = Number(box.dataset.line);
    lines[number] = lines[number].replace(/\[([ xX])\]/, (_, mark) => (mark === " " ? "[x]" : "[ ]"));
    body.value = lines.join("\n");
    box.closest("li").classList.toggle("done", box.checked);
    changed();
  });

  // --- Focus mode: just you and the note. ---
  const focusButton = page.querySelector("[data-focus-mode]");
  function setFocusMode(on) {
    document.body.classList.toggle("focus-mode", on);
    focusButton.setAttribute("aria-pressed", String(on));
    try { localStorage.setItem("focus-mode", on ? "1" : ""); } catch { /* private window: fine */ }
  }
  focusButton.addEventListener("click", () => setFocusMode(!document.body.classList.contains("focus-mode")));
  try { if (localStorage.getItem("focus-mode")) setFocusMode(true); } catch { /* ignore */ }

  // --- Copy as Markdown / plain text ---
  if (navigator.clipboard) {
    page.querySelectorAll("[data-copy]").forEach((button) => {
      button.hidden = false;
      button.addEventListener("click", async () => {
        let text = body.value;
        if (button.dataset.copy === "plain") {
          const response = await post(form.dataset.plainUrl, { body: body.value }).catch(() => null);
          if (!response || !response.ok) return toast("Couldn't copy. Try again.", true);
          text = await response.text();
        }
        await navigator.clipboard.writeText(text);
        button.closest(".sheet")?.hidePopover();
        toast(button.dataset.copy === "plain" ? "Copied as plain text." : "Copied as Markdown.");
      });
    });
  }

  if (!canEdit) return;

  // --- Autosave, with a calm status ---
  let dirty = false;
  let saving = null;       // the save in progress, if any
  let lastSaved = null;    // when the last save worked
  let retryDelay = 2000;   // doubles after each failed try, up to 30 s
  let retryTimer = null;
  let wasComplete = null;  // was the checklist at 100% after the last save?

  function setStatus(text, state = "") {
    statusText.textContent = text;
    status.className = "save-status" + (state ? ` is-${state}` : "");
    retryButton.hidden = state !== "error";
  }
  // "Saved ✓" for a moment, then a quiet "Saved 2 min ago" that keeps up with time.
  let calmTimer = null;
  function showSaved() {
    setStatus("Saved", "saved");
    clearTimeout(calmTimer);
    calmTimer = setTimeout(() => { if (!dirty && !saving) setStatus(`Saved ${sinceText(lastSaved)}`); }, 2500);
  }
  setInterval(() => {
    if (lastSaved && !dirty && !saving && !status.className.includes("is-")) setStatus(`Saved ${sinceText(lastSaved)}`);
  }, 30000);

  async function save() {
    saveSoon.cancel();
    clearTimeout(retryTimer);
    if (saving) await saving; // one save at a time, in order
    if (!dirty) return true;
    dirty = false;
    // Only say "Saving…" if it takes a while: quick saves shouldn't flicker.
    const slow = setTimeout(() => setStatus("Saving…", "saving"), 500);
    saving = post(form.action, new FormData(form))
      .then(async (response) => {
        const result = await response.json().catch(() => ({}));
        if (response.status >= 500) throw new Error("server");
        if (!response.ok) {
          // A problem with what was typed: saying it again won't help, so no retry.
          const isNew = form.action.endsWith("/new");
          if (isNew && result.errors?.body && !result.errors.title) setStatus("New note");
          else setStatus(`Not saved: ${result.errors ? Object.values(result.errors)[0] : result.error || "something's wrong"}`, "error");
          retryButton.hidden = true;
          return false;
        }
        if (form.action !== new URL(result.save_url, location.href).href) {
          // The first save of a new note: from now on, save to its own address.
          form.action = result.save_url;
          history.replaceState(null, "", result.url);
        }
        lastSaved = Date.now();
        retryDelay = 2000;
        updateStats(result);
        updateTextTags(result.tags);
        showSaved();
        return true;
      })
      .catch(() => {
        // Offline or a server hiccup: keep the changes, say so, and try again soon.
        dirty = true;
        setStatus(`Couldn't save — retrying in ${Math.round(retryDelay / 1000)} s`, "error");
        retryTimer = setTimeout(save, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 30000);
        return false;
      })
      .finally(() => { clearTimeout(slow); saving = null; });
    return saving;
  }
  const saveSoon = debounce(save, 900);
  retryButton.addEventListener("click", () => { retryDelay = 2000; save(); });

  function changed() {
    dirty = true;
    saveSoon();
    refreshPreviewSoon();
    grow();
  }

  function updateStats(result) {
    document.getElementById("stat-words").textContent = `${result.words} ${result.words === 1 ? "word" : "words"}`;
    document.getElementById("stat-minutes").textContent = `${result.minutes} min read`;
    const checks = document.getElementById("stat-checks");
    checks.hidden = !result.total;
    checks.innerHTML = `<span aria-hidden="true">·</span> ${result.done}/${result.total} done`;
    const complete = result.total > 0 && result.done === result.total;
    if (complete && wasComplete === false) celebrate(checks);
    wasComplete = complete;
  }

  // The pin and color fields sit outside the <form> (form="note-form"), so
  // their events don't bubble up to it. Listen on the whole document instead.
  document.addEventListener("input", (event) => { if (event.target.form === form) changed(); });
  document.addEventListener("change", (event) => {
    if (event.target.form !== form) return;
    if (event.target.name === "color") {
      page.className = page.className.replace(/note-\w+/, `note-${event.target.value}`);
    }
    if (event.target.type === "radio" || event.target.type === "checkbox") changed();
  });

  /** Save now. With nothing to save, still answer with a little pulse of "Saved". */
  async function saveNow() {
    if (!dirty && !saving && lastSaved !== null) {
      showSaved();
    } else {
      dirty = true;
      await save();
    }
    status.classList.remove("pulse");
    void status.offsetWidth;
    status.classList.add("pulse");
  }

  // The Save button and Ctrl+S save right away, without leaving the page.
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    saveNow();
  });

  // Leaving the page with unsaved changes: sendBeacon() still delivers them
  // after the page is gone.
  window.addEventListener("pagehide", () => {
    if (dirty) navigator.sendBeacon(form.action, new FormData(form));
  });

  const goBack = () => save().then(() => { window.location = page.querySelector("[data-back]").href; });

  // --- Formatting ---

  /**
   * Replace part of the text. insertText goes through the browser's own
   * editing, so Ctrl+Z and Ctrl+Shift+Z undo and redo it like typing.
   */
  function replaceText(start, end, text) {
    body.focus();
    body.setSelectionRange(start, end);
    if (!document.execCommand("insertText", false, text)) {
      body.setRangeText(text, start, end, "end"); // older browsers: works, but without undo
      changed();
    }
  }

  /** Put `before` and `after` around the selection (or the cursor). */
  function wrap(before, after = before) {
    const { selectionStart: start, selectionEnd: end, value } = body;
    replaceText(start, end, before + value.slice(start, end) + after);
    body.setSelectionRange(start + before.length, end + before.length);
  }

  /** Add `prefix` to the start of every selected line, or take it off if all have it. */
  function prefixLines(prefix) {
    const { selectionStart: start, selectionEnd: end, value } = body;
    const lineStart = value.lastIndexOf("\n", start - 1) + 1;
    const lineEnd = value.indexOf("\n", end) === -1 ? value.length : value.indexOf("\n", end);
    const lines = value.slice(lineStart, lineEnd).split("\n");
    const allHave = lines.every((line) => line.startsWith(prefix));
    replaceText(lineStart, lineEnd, lines.map((line) => (allHave ? line.slice(prefix.length) : prefix + line)).join("\n"));
  }

  page.querySelectorAll(".toolbar [data-wrap]").forEach((button) =>
    button.addEventListener("click", () => wrap(button.dataset.wrap)));
  page.querySelectorAll(".toolbar [data-prefix]").forEach((button) =>
    button.addEventListener("click", () => prefixLines(button.dataset.prefix)));
  page.querySelector(".toolbar [data-link]")?.addEventListener("click", () => {
    wrap("[[", "]]");
    showTextSuggestions();
  });

  // --- [[ and # suggestions while typing ---

  let trigger = null; // {kind: "link" | "tag", start, typed}
  const textSuggest = createSuggest((item) => {
    const end = body.selectionStart;
    if (trigger.kind === "link") {
      // Swallow a "]]" that's already there (from the toolbar's link button).
      const closing = body.value.slice(end, end + 2) === "]]" ? 2 : 0;
      replaceText(trigger.start, end + closing, `[[${item.value}]]`);
    } else {
      replaceText(trigger.start, end, `#${item.value} `);
    }
    trigger = null;
  });
  body.setAttribute("aria-controls", textSuggest.list.id);

  function showTextSuggestions() {
    const before = body.value.slice(0, body.selectionStart);
    let match;
    if ((match = before.match(/\[\[([^[\]\n]{0,60})$/))) {
      const typed = match[1];
      trigger = { kind: "link", start: before.length - match[0].length, typed };
      const items = fuzzyFilter(typed, data.titles || []).map((title) => ({ label: title, value: title }));
      const exact = (data.titles || []).some((title) => title.toLowerCase() === typed.trim().toLowerCase());
      if (typed.trim() && !exact) items.push({ label: `Link to new note “${typed.trim()}”`, value: typed.trim(), isNew: true });
      const { x, y } = caretPosition(body);
      textSuggest.show(items, typed, x, y, "Link to a note");
    } else if ((match = before.match(/(^|[\s(])#([\p{L}][\p{L}\p{N}_-]{0,29})?$/u))) {
      const typed = (match[2] || "").toLowerCase();
      trigger = { kind: "tag", start: before.length - typed.length - 1, typed };
      const items = fuzzyFilter(typed, data.tags || []).map((name) => ({ label: `#${name}`, value: name }));
      if (typed && !(data.tags || []).includes(typed)) items.push({ label: `New tag #${typed}`, value: typed, isNew: true });
      const { x, y } = caretPosition(body);
      textSuggest.show(items, typed, x, y, "Add a tag");
    } else {
      trigger = null;
      textSuggest.hide();
    }
  }
  body.addEventListener("input", showTextSuggestions);
  body.addEventListener("click", showTextSuggestions);
  body.addEventListener("blur", () => setTimeout(() => textSuggest.hide(), 150));

  body.addEventListener("keydown", (event) => {
    const ctrl = event.ctrlKey || event.metaKey;

    if (textSuggest.isOpen) {
      if (event.key === "ArrowDown") { event.preventDefault(); return textSuggest.move(1); }
      if (event.key === "ArrowUp") { event.preventDefault(); return textSuggest.move(-1); }
      if (event.key === "Enter" || event.key === "Tab") { event.preventDefault(); return textSuggest.pick(); }
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); return textSuggest.hide(); }
    }

    if (ctrl && event.key.toLowerCase() === "b") { event.preventDefault(); wrap("**"); }
    if (ctrl && event.key.toLowerCase() === "i") { event.preventDefault(); wrap("*"); }

    // Enter in a list starts the next item. Enter on an empty item ends the list.
    if (event.key === "Enter" && !event.shiftKey && !ctrl) {
      const { selectionStart: start, value } = body;
      const lineStart = value.lastIndexOf("\n", start - 1) + 1;
      const line = value.slice(lineStart, start);
      const match = line.match(/^(\s*)([-*+] \[[ xX]\] |[-*+] |(\d+)[.)] |> )/);
      if (!match) return;
      event.preventDefault();
      if (line.trim() === match[2].trim()) {
        replaceText(lineStart, start, ""); // an empty item: stop the list
      } else {
        let marker = match[2].replace(/\[[xX]\]/, "[ ]");
        if (match[3]) marker = marker.replace(match[3], String(Number(match[3]) + 1));
        replaceText(start, body.selectionEnd, "\n" + match[1] + marker);
      }
    }
  });

  document.addEventListener("keydown", (event) => {
    const ctrl = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();
    if (ctrl && key === "s") {
      event.preventDefault();
      saveNow();
    } else if (ctrl && key === "enter") {
      event.preventDefault();
      goBack(); // save and close
    } else if (ctrl && key === "e") {
      event.preventDefault();
      setMode(panes.dataset.mode === "write" ? "preview" : "write");
    } else if (ctrl && event.shiftKey && key === "f") {
      event.preventDefault();
      setFocusMode(!document.body.classList.contains("focus-mode"));
    } else if (event.key === "Escape" && event.target !== searchBox && !openSheet() && !textSuggest.isOpen) {
      event.preventDefault();
      // Esc steps out of focus mode first, then back to the list (after saving).
      if (document.body.classList.contains("focus-mode")) setFocusMode(false);
      else goBack();
    }
  });

  // --- The tag box becomes chips ---
  const updateTextTags = setUpTagChips(document.getElementById("tags"), changed, data.tags || []);
}

/**
 * Turn the plain "work, ideas" text box into chips with × buttons and
 * suggestions. The original box becomes hidden and keeps the value the
 * form sends. Tags that come from #tags in the text show as dotted chips
 * marked "from text": they're removed by editing the text, not here.
 * Returns a function that updates those "from text" chips after a save.
 */
function setUpTagChips(field, onChange, knownTags) {
  if (!field) return () => {};
  const box = field.closest(".tags-field");
  const typing = document.createElement("input");
  typing.type = "text";
  typing.placeholder = field.placeholder;
  typing.setAttribute("aria-label", "Add a tag");
  typing.setAttribute("autocomplete", "off");
  typing.disabled = field.disabled;
  field.type = "hidden";
  const manageLink = box.querySelector(".tags-manage");
  if (manageLink) manageLink.before(typing);
  else box.append(typing);

  const split = (text) => text.split(/[\s,]+/).map((tag) => tag.replace(/^#/, "").toLowerCase()).filter(Boolean);
  const tags = split(field.value);
  let textTags = split(field.dataset.textTags || "");
  const colors = ["blue", "purple", "pink", "red", "orange", "yellow", "green", "teal"];
  // Same color rule as tag_color() in tags.py: the sum of the letters' codes.
  const colorOf = (tag) => colors[[...tag].reduce((sum, letter) => sum + letter.codePointAt(0), 0) % colors.length];

  function draw() {
    box.querySelectorAll(".chip").forEach((chip) => chip.remove());
    tags.forEach((tag, index) => {
      const chip = document.createElement("span");
      chip.className = `chip tag-${colorOf(tag)}`;
      chip.textContent = `#${tag}`;
      if (!typing.disabled) {
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "chip-remove";
        remove.setAttribute("aria-label", `Remove #${tag}`);
        remove.textContent = "×";
        remove.addEventListener("click", () => {
          tags.splice(index, 1);
          update();
          typing.focus();
        });
        chip.append(remove);
      }
      typing.before(chip);
    });
    textTags.filter((tag) => !tags.includes(tag)).forEach((tag) => {
      const chip = document.createElement("span");
      chip.className = `chip chip-derived tag-${colorOf(tag)}`;
      chip.title = `From #${tag} in the text. Edit the text to remove it.`;
      chip.textContent = `#${tag} · from text`;
      typing.before(chip);
    });
    typing.placeholder = tags.length || textTags.length ? "Add a tag" : field.placeholder;
  }

  function update() {
    field.value = tags.join(", ");
    draw();
    onChange();
  }

  function add(text) {
    let changedAny = false;
    for (const tag of split(text)) {
      if (!tags.includes(tag)) { tags.push(tag); changedAny = true; }
    }
    typing.value = "";
    suggest.hide();
    if (changedAny) update();
  }

  const suggest = createSuggest((item) => add(item.value));
  typing.setAttribute("aria-controls", suggest.list.id);
  function showSuggestions() {
    const typed = typing.value.trim().replace(/^#/, "").toLowerCase();
    const options = knownTags.filter((tag) => !tags.includes(tag));
    const items = fuzzyFilter(typed, options).map((tag) => ({ label: `#${tag}`, value: tag }));
    if (typed && !knownTags.includes(typed) && !tags.includes(typed)) {
      items.push({ label: `Create #${typed}`, value: typed, isNew: true });
    }
    const rect = typing.getBoundingClientRect();
    suggest.show(items, typed, rect.left + window.scrollX, rect.bottom + window.scrollY - 4);
  }

  typing.addEventListener("keydown", (event) => {
    if (suggest.isOpen && event.key === "ArrowDown") { event.preventDefault(); return suggest.move(1); }
    if (suggest.isOpen && event.key === "ArrowUp") { event.preventDefault(); return suggest.move(-1); }
    if (suggest.isOpen && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); return suggest.hide(); }
    if (event.key === "Enter" && suggest.isOpen && typing.value.trim()) { event.preventDefault(); return suggest.pick(); }
    if ([",", " ", "Enter"].includes(event.key) && typing.value.trim()) {
      event.preventDefault();
      add(typing.value);
    } else if (event.key === "Enter") {
      event.preventDefault(); // don't submit the form from the tag box
    } else if (event.key === "Backspace" && !typing.value && tags.length) {
      tags.pop();
      update();
    }
  });
  typing.addEventListener("focus", showSuggestions);
  typing.addEventListener("input", (event) => {
    // The typing box isn't part of the form's data, so this isn't a change to the note.
    event.stopPropagation();
    showSuggestions();
  });
  typing.addEventListener("blur", () => {
    setTimeout(() => suggest.hide(), 150);
    if (typing.value.trim()) add(typing.value);
  });
  draw();

  // After a save, the server says which tags the note has. The ones not in
  // the box came from the text.
  return (allTags) => {
    if (!allTags) return;
    textTags = allTags.filter((tag) => !tags.includes(tag));
    draw();
  };
}
