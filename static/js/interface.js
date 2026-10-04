"use strict";

// Only filter records that the server has authorized for this account.
document.querySelectorAll(".task-workspace").forEach((workspace) => {
  const cards = [...workspace.querySelectorAll(".task-card")];
  const tools = workspace.querySelector(".task-tools");
  if (!cards.length || !tools) return;
  const search = tools.querySelector(".task-search");
  const tabs = [...tools.querySelectorAll("[data-filter]")];
  const empty = workspace.querySelector(".filter-empty");
  const feedback = workspace.querySelector(".filter-feedback");
  let selected = "全部";
  tools.hidden = false;

  function readQuery() {
    const params = new URLSearchParams(location.search);
    search.value = (params.get("q") || "").slice(0, 100);
    selected = tabs.some(tab => tab.dataset.filter === params.get("state")) ? params.get("state") : "全部";
  }
  function applyFilters(updateURL = true) {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    cards.forEach((card) => {
      const matches = (selected === "全部" || card.dataset.taskState === selected)
        && card.dataset.search.toLocaleLowerCase().includes(query);
      card.hidden = !matches;
      if (matches) visible++;
      else {
        const map = card.querySelector(".fence-map");
        if (map) map.open = false;
      }
    });
    tabs.forEach((tab) => {
      const active = tab.dataset.filter === selected;
      tab.classList.toggle("selected", active);
      tab.setAttribute("aria-pressed", String(active));
    });
    document.querySelectorAll("[data-count-state]").forEach(counter => {
      counter.textContent = cards.filter(card => card.dataset.taskState === counter.dataset.countState).length;
    });
    empty.hidden = visible > 0;
    feedback.hidden = !query && selected === "全部";
    feedback.textContent = `显示 ${visible} / ${cards.length} 项任务`;
    // Preserve context on both direct result links and the browser's Back action.
    const url = new URL(location.href);
    if (selected === "全部") url.searchParams.delete("state");
    else url.searchParams.set("state", selected);
    if (query) url.searchParams.set("q", search.value.trim());
    else url.searchParams.delete("q");
    if (updateURL) history.replaceState(null, "", url);
    workspace.querySelectorAll("[data-task-link]").forEach(link => {
      const target = new URL(link.href);
      target.searchParams.set("state", selected);
      target.searchParams.set("q", search.value.trim());
      link.href = target.href;
    });
  }
  tabs.forEach((tab) => tab.addEventListener("click", () => {
    selected = tab.dataset.filter;
    applyFilters();
  }));
  document.querySelectorAll("[data-quick-filter]").forEach(link => link.addEventListener("click", event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    selected = link.dataset.quickFilter;
    search.value = "";
    applyFilters();
    workspace.scrollIntoView({ block: "start" });
  }));
  search.addEventListener("input", () => applyFilters());
  workspace.querySelector(".filter-reset").addEventListener("click", () => {
    selected = "全部";
    search.value = "";
    applyFilters();
    search.focus();
  });
  workspace.addEventListener("attendance:checked-in", () => {
    selected = "全部";
    applyFilters();
  });
  window.addEventListener("popstate", () => { readQuery(); applyFilters(false); });
  readQuery();
  applyFilters();
});

document.querySelectorAll("[data-roster]").forEach(panel => {
  const rows = [...panel.querySelectorAll("[data-attendance-row]")];
  if (!rows.length) return;
  const toolbar = panel.querySelector(".roster-tools");
  const search = toolbar.querySelector("input");
  const state = toolbar.querySelector("select");
  toolbar.hidden = false;
  const filter = () => {
    let visible = 0;
    rows.forEach(row => {
      row.hidden = !(row.dataset.search.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())
        && (state.value === "all" || row.dataset.attendance === state.value));
      if (!row.hidden) visible++;
    });
    panel.querySelector(".roster-empty").hidden = visible > 0;
    panel.querySelector(".roster-count").textContent = `显示 ${visible} / ${rows.length} 人`;
  };
  search.addEventListener("input", filter);
  state.addEventListener("change", filter);
  panel.querySelector(".roster-reset").addEventListener("click", () => {
    search.value = ""; state.value = "all"; filter(); search.focus();
  });
  filter();
});

// Native validation runs before submit; only disable the actual submit control.
document.querySelectorAll("[data-submit-guard]").forEach(form => {
  let submitting = false;
  const buttons = [...form.querySelectorAll('button[type="submit"]')];
  const originals = buttons.map(button => ({disabled: button.disabled, nodes: [...button.childNodes].map(node => node.cloneNode(true))}));
  form.addEventListener("submit", event => {
    if (submitting) { event.preventDefault(); return; }
    submitting = true;
    buttons.forEach(button => { button.disabled = true; button.setAttribute("aria-busy", "true"); button.textContent = "正在提交…"; });
  });
  window.addEventListener("pageshow", () => {
    submitting = false;
    buttons.forEach((button, index) => {
      button.disabled = originals[index].disabled;
      button.removeAttribute("aria-busy");
      button.replaceChildren(...originals[index].nodes.map(node => node.cloneNode(true)));
    });
  });
});
document.querySelector("[data-form-error]")?.focus();

const passwordToggle = document.querySelector(".password-toggle");
if (passwordToggle) {
  passwordToggle.hidden = false;
  passwordToggle.addEventListener("click", () => {
    const input = document.getElementById(passwordToggle.getAttribute("aria-controls"));
    const reveal = input.type === "password";
    input.type = reveal ? "text" : "password";
    passwordToggle.textContent = reveal ? "隐藏密码" : "显示密码";
    passwordToggle.setAttribute("aria-pressed", String(reveal));
  });
  const roleHint = document.querySelector(".login-role-hint");
  const describeRole = () => {
    const teacher = document.querySelector('input[name="role"]:checked').value === "teacher";
    roleHint.textContent = teacher ? "教师：使用工号登录，发布任务和管理班级考勤。" : "学生：使用学号登录，完成定位签到和查看个人记录。";
  };
  document.querySelectorAll('input[name="role"]').forEach(input => input.addEventListener("change", describeRole));
  describeRole();
}

document.querySelectorAll("[data-enhanced]").forEach(element => { element.hidden = false; });
document.querySelectorAll("[data-radius-value]").forEach(button => button.addEventListener("click", () => {
  const input = button.closest("form").elements.namedItem("radius_meters");
  input.value = button.dataset.radiusValue;
  input.dispatchEvent(new Event("input", {bubbles: true}));
}));
document.querySelectorAll("[data-duration]").forEach(button => button.addEventListener("click", () => {
  const form = button.closest("form");
  const start = form.elements.namedItem("start_time");
  const end = form.elements.namedItem("end_time");
  // Treat the input as a wall-clock string; do not depend on the device timezone.
  const time = Date.parse(start.value + "Z");
  if (!Number.isFinite(time)) { start.focus(); start.reportValidity(); return; }
  const value = new Date(time + Number(button.dataset.duration) * 60000).toISOString();
  if (/^\d{4}-/.test(value)) end.value = value.slice(0, 16);
}));
