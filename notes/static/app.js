/*
  Forget-Me-Note's JavaScript. Every page works without it (forms post and
  the server answers with a page). This file makes things smoother:

  - the editor saves as you type, shows a live preview, and turns the tag
    box into chips
  - checkboxes on cards tick without a page reload
  - keyboard shortcuts, toasts that fade away, and "Are you sure?" prompts

  Requests sent with fetch() carry "X-Requested-With: fetch", so the server
  answers with a little JSON instead of a whole page (see is_fetch()).
*/
"use strict";

const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

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
    timer = setTimeout(() => fn(...args), wait);
  };
  debounced.cancel = () => clearTimeout(timer);
  return debounced;
}

/** Show a short message at the bottom, like the server's flash() toasts. */
function toast(message, isError = false) {
  const box = document.querySelector(".toasts");
  const item = document.createElement("p");
  item.className = "toast" + (isError ? " toast-error" : "");
  item.setAttribute("role", isError ? "alert" : "status");
  item.textContent = message;
  box.append(item);
  fadeOut(item, isError ? 7000 : 3500);
}

function fadeOut(item, delay) {
  setTimeout(() => {
    item.classList.add("is-leaving");
    setTimeout(() => item.remove(), 300);
  }, delay);
}

/** True while the person is typing in a box, so single-key shortcuts stay out of the way. */
function isTyping(target) {
  return target.closest("input, textarea, select, [contenteditable]") !== null;
}

// ---------- Toasts and confirmations ----------

// Messages fade by themselves. Errors stay longer; ones with Undo too.
document.querySelectorAll(".toasts .toast").forEach((item) => {
  const lasting = item.classList.contains("toast-error") || item.querySelector("form");
  fadeOut(item, lasting ? 8000 : 4000);
});

// <form data-confirm="Delete this?"> asks first.
document.addEventListener("submit", (event) => {
  const question = event.target.dataset.confirm;
  if (question && !window.confirm(question)) event.preventDefault();
});

// ---------- Keyboard shortcuts ----------

const searchBox = document.getElementById("search");

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
  }
});

// ---------- Checkboxes on cards ----------

document.querySelectorAll(".note-card[data-check-url]").forEach((card) => {
  card.addEventListener("change", async (event) => {
    const box = event.target;
    if (!box.matches(".checklist input[type=checkbox]")) return;
    box.closest("li").classList.toggle("done", box.checked);
    const response = await post(card.dataset.checkUrl, { line: box.dataset.line }).catch(() => null);
    if (!response || !response.ok) {
      // Put it back the way it was: the server didn't save it.
      box.checked = !box.checked;
      box.closest("li").classList.toggle("done", box.checked);
      toast("Couldn't save that. Reload the page and try again.", true);
      return;
    }
    const { done, total } = await response.json();
    const bar = card.querySelector(".progress-bar span");
    if (bar) bar.style.width = `${Math.round((done * 100) / total)}%`;
    const text = card.querySelector(".progress-text");
    if (text) text.textContent = `${done}/${total}`;
  });
});

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

// ---------- The editor ----------

const form = document.getElementById("note-form");
if (form) setUpEditor(form);

function setUpEditor(form) {
  const page = document.getElementById("editor-page");
  const body = document.getElementById("body");
  const preview = document.getElementById("preview");
  const panes = document.getElementById("panes");
  const status = document.getElementById("save-status");
  const canEdit = form.hasAttribute("data-autosave");

  // --- The textarea grows with its text, so the page scrolls, not the box. ---
  const grow = () => {
    body.style.height = "auto";
    body.style.height = `${body.scrollHeight + 2}px`;
  };
  body.addEventListener("input", grow);
  grow();

  // --- Write / Split / Preview, remembered for next time. ---
  const modeButtons = page.querySelectorAll("[data-mode]");
  function setMode(mode) {
    panes.dataset.mode = mode;
    modeButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.mode === mode)));
    try { localStorage.setItem("editor-mode", mode); } catch { /* private window: fine */ }
    if (mode !== "write") refreshPreview();
    else body.focus();
  }
  modeButtons.forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
  let savedMode = "write";
  try { savedMode = localStorage.getItem("editor-mode") || "write"; } catch { /* ignore */ }
  // A note in the Trash can't be edited, so show it read-only, as a preview.
  setMode(canEdit ? savedMode : "preview");

  // --- Live preview, drawn by the same Python renderer as the cards. ---
  async function refreshPreview() {
    if (panes.dataset.mode === "write") return;
    const response = await post(form.dataset.previewUrl, { body: body.value }).catch(() => null);
    if (response && response.ok) {
      const html = await response.text();
      preview.innerHTML = html.trim() ? html : '<p class="hint">Nothing to preview yet.</p>';
    }
  }
  const refreshPreviewSoon = debounce(refreshPreview, 250);

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

  if (!canEdit) return;

  // --- Autosave ---
  let dirty = false;
  let saving = null; // the save in progress, if any

  function setStatus(text, state) {
    status.textContent = text;
    status.className = "save-status" + (state ? ` is-${state}` : "");
  }

  async function save() {
    saveSoon.cancel();
    if (saving) await saving; // one save at a time, in order
    if (!dirty) return true;
    dirty = false;
    setStatus("Saving…", "saving");
    saving = post(form.action, new FormData(form))
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          const message = data.errors ? Object.values(data.errors)[0] : data.error || "Couldn't save.";
          // An empty new note isn't an error worth shouting about.
          setStatus(form.action.endsWith("/new") && data.errors?.body && !data.errors.title ? "New note" : `Not saved: ${message}`,
                    form.action.endsWith("/new") ? "" : "error");
          return false;
        }
        if (form.action !== new URL(data.save_url, location.href).href) {
          // The first save of a new note: from now on, save to its own address.
          form.action = data.save_url;
          history.replaceState(null, "", data.url);
        }
        updateStats(data);
        setStatus("Saved", "saved");
        return true;
      })
      .catch(() => {
        dirty = true; // try again with the next change
        setStatus("Offline: not saved yet", "error");
        return false;
      })
      .finally(() => { saving = null; });
    return saving;
  }
  const saveSoon = debounce(save, 900);

  function changed() {
    dirty = true;
    setStatus("Editing…", "");
    saveSoon();
    refreshPreviewSoon();
    grow();
  }

  function updateStats(data) {
    document.getElementById("stat-words").textContent = `${data.words} ${data.words === 1 ? "word" : "words"}`;
    document.getElementById("stat-minutes").textContent = `${data.minutes} min read`;
    const checks = document.getElementById("stat-checks");
    checks.hidden = !data.total;
    checks.innerHTML = `<span aria-hidden="true">·</span> ${data.done}/${data.total} done`;
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

  // The Save button and Ctrl+S save right away, without leaving the page.
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    dirty = true;
    save();
  });

  // Leaving the page with unsaved changes: sendBeacon() still delivers them
  // after the page is gone.
  window.addEventListener("pagehide", () => {
    if (dirty) navigator.sendBeacon(form.action, new FormData(form));
  });

  // --- Formatting ---

  /** Put `before` and `after` around the selection (or the cursor). */
  function wrap(before, after = before) {
    const { selectionStart: start, selectionEnd: end, value } = body;
    const selected = value.slice(start, end);
    body.setRangeText(before + selected + after, start, end, "select");
    body.setSelectionRange(start + before.length, end + before.length);
    body.focus();
    changed();
  }

  /** Add `prefix` to the start of every selected line, or take it off if all have it. */
  function prefixLines(prefix) {
    const { selectionStart: start, selectionEnd: end, value } = body;
    const lineStart = value.lastIndexOf("\n", start - 1) + 1;
    const lineEnd = value.indexOf("\n", end) === -1 ? value.length : value.indexOf("\n", end);
    const lines = value.slice(lineStart, lineEnd).split("\n");
    const allHave = lines.every((line) => line.startsWith(prefix));
    const result = lines.map((line) => (allHave ? line.slice(prefix.length) : prefix + line)).join("\n");
    body.setRangeText(result, lineStart, lineEnd, "end");
    body.focus();
    changed();
  }

  page.querySelectorAll(".toolbar [data-wrap]").forEach((button) =>
    button.addEventListener("click", () => wrap(button.dataset.wrap)));
  page.querySelectorAll(".toolbar [data-prefix]").forEach((button) =>
    button.addEventListener("click", () => prefixLines(button.dataset.prefix)));
  page.querySelector(".toolbar [data-link]")?.addEventListener("click", () => wrap("[[", "]]"));

  body.addEventListener("keydown", (event) => {
    const ctrl = event.ctrlKey || event.metaKey;
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
        body.setRangeText("", lineStart, start, "end"); // an empty item: stop the list
      } else {
        let marker = match[2].replace(/\[[xX]\]/, "[ ]");
        if (match[3]) marker = marker.replace(match[3], String(Number(match[3]) + 1));
        body.setRangeText("\n" + match[1] + marker, start, body.selectionEnd, "end");
      }
      changed();
    }
  });

  document.addEventListener("keydown", (event) => {
    const ctrl = event.ctrlKey || event.metaKey;
    if (ctrl && event.key.toLowerCase() === "s") {
      event.preventDefault();
      dirty = true;
      save();
    } else if (ctrl && event.key.toLowerCase() === "e") {
      event.preventDefault();
      setMode(panes.dataset.mode === "write" ? "preview" : "write");
    } else if (event.key === "Escape" && event.target !== searchBox && !document.querySelector(":popover-open")) {
      // Save first, then go back to the list.
      event.preventDefault();
      save().then(() => { window.location = page.querySelector("[data-back]").href; });
    }
  });

  // --- The tag box becomes chips ---
  setUpTagChips(document.getElementById("tags"), changed);
}

/**
 * Turn the plain "work, ideas" text box into chips with × buttons.
 * The original box becomes hidden and keeps the value the form sends.
 */
function setUpTagChips(field, onChange) {
  if (!field) return;
  const box = field.closest(".tags-field");
  const typing = document.createElement("input");
  typing.type = "text";
  typing.placeholder = field.placeholder;
  typing.setAttribute("aria-label", "Add a tag");
  typing.setAttribute("autocomplete", "off");
  typing.setAttribute("list", field.getAttribute("list"));
  typing.disabled = field.disabled;
  field.type = "hidden";
  field.removeAttribute("list");
  box.append(typing);

  const tags = field.value.split(/[\s,]+/).map((tag) => tag.replace(/^#/, "").toLowerCase()).filter(Boolean);

  function draw() {
    box.querySelectorAll(".chip").forEach((chip) => chip.remove());
    tags.forEach((tag, index) => {
      const chip = document.createElement("span");
      // Same color rule as tag_color() in tags.py: the sum of the letters' codes.
      const colors = ["blue", "purple", "pink", "red", "orange", "yellow", "green", "teal"];
      const sum = [...tag].reduce((total, letter) => total + letter.codePointAt(0), 0);
      chip.className = `chip tag-${colors[sum % colors.length]}`;
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
    typing.placeholder = tags.length ? "Add a tag" : field.placeholder;
  }

  function update() {
    field.value = tags.join(", ");
    draw();
    onChange();
  }

  function addTyped() {
    const added = typing.value.split(/[\s,]+/).map((tag) => tag.replace(/^#/, "").toLowerCase()).filter(Boolean);
    typing.value = "";
    let changedAny = false;
    for (const tag of added) {
      if (!tags.includes(tag)) { tags.push(tag); changedAny = true; }
    }
    if (changedAny) update();
  }

  typing.addEventListener("keydown", (event) => {
    if (["Enter", ",", " ", "Tab"].includes(event.key) && typing.value.trim()) {
      event.preventDefault();
      addTyped();
    } else if (event.key === "Enter") {
      event.preventDefault(); // don't submit the form from the tag box
    } else if (event.key === "Backspace" && !typing.value && tags.length) {
      tags.pop();
      update();
    }
  });
  // Picking a suggestion from the list fills the box: add it straight away.
  typing.addEventListener("change", () => { if (typing.value.trim()) addTyped(); });
  typing.addEventListener("blur", () => { if (typing.value.trim()) addTyped(); });
  // The typing box isn't part of the form's data, so its own input events
  // shouldn't count as a change to the note.
  typing.addEventListener("input", (event) => event.stopPropagation());
  draw();
}
