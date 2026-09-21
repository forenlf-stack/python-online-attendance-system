"use strict";

function currentPosition() {
  return new Promise((resolve, reject) => {
    if (!window.isSecureContext) {
      reject(new Error("当前页面不是安全上下文，请使用本机 localhost 或可信 HTTPS。"));
      return;
    }
    if (!navigator.geolocation) {
      reject(new Error("浏览器不支持定位，请更换支持定位的浏览器。"));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, (error) => {
      const messages = {
        1: "定位权限被拒绝，请在浏览器和系统设置中允许位置访问后重试。",
        2: "暂时无法获取位置，请检查设备定位服务或更换环境后重试。",
        3: "定位超时，请移动至信号较好的位置后重试。"
      };
      reject(new Error(messages[error.code] || "定位失败，请稍后重试。"));
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
  });
}

function accuracyText(accuracy, radius) {
  const poor = accuracy > Math.min(radius, 100);
  return `定位精度估计：约 ${Math.round(accuracy)} 米。${poor ? "精度较差，建议重新定位或更换环境；签到半径保持不变。" : ""}`;
}

const centerButton = document.getElementById("locate-center");
if (centerButton) {
  centerButton.addEventListener("click", async () => {
    const feedback = document.getElementById("center-feedback");
    centerButton.disabled = true;
    feedback.textContent = "定位中，请允许浏览器访问位置…";
    try {
      const { coords } = await currentPosition();
      document.getElementById("center-latitude").value = coords.latitude;
      document.getElementById("center-longitude").value = coords.longitude;
      centerButton.closest("form").dispatchEvent(new CustomEvent("attendance:center"));
      feedback.textContent = "已填入当前位置。" + accuracyText(coords.accuracy, 100);
    } catch (error) {
      feedback.textContent = error.message;
    } finally {
      centerButton.disabled = false;
    }
  });
}

document.querySelectorAll(".checkin-button").forEach((button) => {
  button.addEventListener("click", async () => {
    const card = button.closest(".task-card");
    const feedback = card.querySelector(".checkin-feedback");
    const accuracy = card.querySelector(".location-accuracy");
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    feedback.classList.remove("is-success", "is-error");
    button.textContent = "定位中…";
    feedback.textContent = "正在请求本次位置，请允许浏览器访问。";
    accuracy.textContent = "";
    const map = card.querySelector(".fence-map");
    map?.dispatchEvent(new CustomEvent("attendance:clear-position"));
    let success = false;
    try {
      const { coords } = await currentPosition();
      map?.dispatchEvent(new CustomEvent("attendance:position", { detail: {
        latitude: coords.latitude, longitude: coords.longitude, accuracy: coords.accuracy
      } }));
      accuracy.textContent = accuracyText(coords.accuracy, Number(button.dataset.radius));
      feedback.textContent = "已获取位置，正在提交签到…";
      button.textContent = "提交中…";
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 15000);
      let response;
      let result;
      try {
        response = await fetch(button.dataset.url, {
          method: "POST", credentials: "same-origin", signal: controller.signal,
          headers: { "Content-Type": "application/json", "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content },
          body: JSON.stringify({ latitude: coords.latitude, longitude: coords.longitude })
        });
        result = await response.json();
      } finally {
        clearTimeout(timer);
      }
      if (!response.ok || !result.success) throw new Error(result.message || "签到失败，请稍后重试。");
      success = true;
      feedback.textContent = result.message;
      feedback.classList.add("is-success");
      card.querySelector("[data-state]").textContent = "已签到";
      card.querySelector("[data-state]").classList.add("done");
      card.dataset.taskState = "已签到";
      card.dispatchEvent(new CustomEvent("attendance:checked-in", { bubbles: true }));
    } catch (error) {
      feedback.classList.add("is-error");
      feedback.textContent = error.name === "AbortError" ? "网络请求超时，可先查看个人记录，再重试。" :
        error instanceof TypeError || error instanceof SyntaxError ? "网络或服务器请求失败，请检查连接后重试。" : error.message;
    } finally {
      button.disabled = success;
      button.removeAttribute("aria-busy");
      button.textContent = success ? "已签到" : "重新定位并签到";
    }
  });
});
