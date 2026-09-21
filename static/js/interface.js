"use strict";

// Filters only operate on the server-authorized task list.
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
  function applyFilters() {
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
    empty.hidden = visible > 0;
    feedback.hidden = !query && selected === "全部";
    feedback.textContent = `显示 ${visible} / ${cards.length} 项任务`;
  }
  tabs.forEach((tab) => tab.addEventListener("click", () => {
    selected = tab.dataset.filter;
    applyFilters();
  }));
  search.addEventListener("input", applyFilters);
  workspace.querySelector(".filter-reset").addEventListener("click", () => {
    selected = "全部";
    search.value = "";
    applyFilters();
    search.focus();
  });
  workspace.addEventListener("attendance:checked-in", () => {
    // Keep a completed card visible so its success feedback can be read.
    selected = "全部";
    applyFilters();
  });
});
