"use strict";

// Map calculations are display-only. Python remains the authority for check-in.
(() => {
  const radians = (degrees) => degrees * Math.PI / 180;
  const number = (value) => value === null || value === undefined || String(value).trim() === "" ? NaN : Number(value);
  const validPoint = (lat, lon) => Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;

  function displayDistance(center, position) {
    const lat1 = radians(center.latitude), lat2 = radians(position.latitude);
    const a = Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2)
      * Math.sin(radians(position.longitude - center.longitude) / 2) ** 2;
    return 2 * 6371000 * Math.asin(Math.sqrt(Math.max(0, Math.min(1, a))));
  }

  class FenceMap {
    constructor(root) {
      this.root = root;
      this.canvas = root.querySelector(".map-canvas");
      this.placeholder = root.querySelector(".map-placeholder");
      this.retryButton = root.querySelector(".map-retry");
      this.fitButton = root.querySelector(".map-fit");
      this.status = root.querySelector(".map-status");
      this.positionText = root.querySelector(".map-position");
      this.failed = false;
      this.position = null;
      this.map = null;
      this.tiles = null;
      this.layers = null;
      this.root.addEventListener("toggle", () => {
        if (this.root.open) this.render();
        else this.stopTiles();
      });
      this.retryButton.addEventListener("click", () => {
        this.failed = false;
        this.stopTiles();
        this.render();
      });
      this.fitButton.addEventListener("click", () => this.render());
      root.addEventListener("attendance:position", (event) => {
        this.position = event.detail;
        this.root.open = true;
        this.render();
      });
      root.addEventListener("attendance:clear-position", () => {
        this.position = null;
        this.render();
      });
      if (root.dataset.form === "true") {
        this.form = root.closest("form");
        this.form.addEventListener("input", (event) => {
          if (!["center_latitude", "center_longitude", "radius_meters"].includes(event.target.name)) return;
          clearTimeout(this.inputTimer);
          this.inputTimer = setTimeout(() => this.render(), 350);
        });
        // Programmatic geolocation fills do not emit native input events.
        this.form.addEventListener("attendance:center", () => this.render());
      }
      this.render();
    }

    readFence() {
      const field = (name) => this.form.elements.namedItem(name).value;
      return {
        latitude: number(this.form ? field("center_latitude") : this.root.dataset.latitude),
        longitude: number(this.form ? field("center_longitude") : this.root.dataset.longitude),
        radius: number(this.form ? field("radius_meters") : this.root.dataset.radius)
      };
    }

    stopTiles() {
      clearTimeout(this.tileTimer);
      if (this.tiles && this.map) {
        this.tiles.off();
        this.map.removeLayer(this.tiles);
      }
      this.tiles = null;
    }

    showMessage(message, isError = false) {
      this.stopTiles();
      this.canvas.hidden = true;
      this.placeholder.hidden = false;
      this.status.textContent = message;
      this.root.dataset.loadState = isError ? "error" : "empty";
      this.placeholder.querySelector(".map-placeholder-title").textContent = isError ? "地图暂时无法显示" : "设置签到中心";
      this.retryButton.hidden = !isError;
      this.retryButton.disabled = false;
      this.fitButton.disabled = true;
    }

    updatePositionText(fence) {
      if (!this.position) {
        this.positionText.textContent = this.form ? "调整中心或半径，地图范围会同步更新。" : "";
        return;
      }
      const position = this.position;
      const distance = Number.isFinite(position.distance) ? position.distance : displayDistance(fence, position);
      const accuracy = Number.isFinite(position.accuracy) ? `；定位精度约 ${Math.round(position.accuracy)} 米` : "";
      this.positionText.textContent = `${position.record ? "所选记录" : "本次位置"}距中心约 ${distance.toFixed(2)} 米${accuracy}。`;
    }

    render() {
      if (!this.root.open) return;
      const fence = this.readFence();
      if (!validPoint(fence.latitude, fence.longitude) || !Number.isFinite(fence.radius) || fence.radius <= 0) {
        this.failed = false;
        this.positionText.textContent = "";
        this.showMessage("获取当前位置或填写有效中心和半径后，即可预览地图。");
        return;
      }
      if (this.position && !validPoint(this.position.latitude, this.position.longitude)) this.position = null;
      this.updatePositionText(fence);
      if (!window.L) {
        this.showMessage("地图组件未加载，请刷新页面；仍可正常提交签到。", true);
        return;
      }
      if (Math.abs(fence.latitude) > 85 || fence.radius > 2000000 ||
          (this.position && Math.abs(this.position.latitude) > 85)) {
        this.showMessage("当前范围超出在线地图显示能力，签到仍按设定范围校验。", true);
        return;
      }
      if (this.failed) return; // Retry only on explicit action, not every position update.
      try {
        this.drawOnline(fence);
      } catch (error) {
        this.failed = true;
        this.showMessage("地图暂时不可用，请重试；仍可正常提交签到。", true);
      }
    }

    drawOnline(fence) {
      this.canvas.hidden = false;
      this.placeholder.hidden = true;
      this.retryButton.hidden = true;
      this.fitButton.disabled = false;
      if (!this.map) {
        this.map = L.map(this.canvas, { scrollWheelZoom: false, minZoom: 1, maxZoom: 19 });
        // Circle bounds depend on projection; initialize the view before adding overlays.
        this.map.setView([fence.latitude, fence.longitude], 16);
        this.map.zoomControl.setPosition("topright");
        L.control.scale({ imperial: false }).addTo(this.map);
        this.layers = L.featureGroup().addTo(this.map);
      }
      this.map.invalidateSize({ pan: false });
      this.layers.clearLayers();
      const center = [fence.latitude, fence.longitude];
      const circle = L.circle(center, { radius: fence.radius, color: "#245fc0", weight: 2,
        fillColor: "#4788e8", fillOpacity: 0.16 }).addTo(this.layers);
      L.circleMarker(center, { radius: 5, color: "#fff", weight: 2, fillColor: "#245fc0", fillOpacity: 1 })
        .bindTooltip("签到中心").addTo(this.layers);
      const bounds = circle.getBounds();
      if (this.position) {
        const position = this.position;
        // Use the nearest world copy around the date line.
        const longitude = fence.longitude + ((position.longitude - fence.longitude + 540) % 360) - 180;
        const point = [position.latitude, longitude];
        L.circleMarker(point, { radius: 7, color: "#fff", weight: 2, fillColor: "#d06724", fillOpacity: 1 })
          .bindTooltip(position.record ? "所选签到记录" : "本次定位").addTo(this.layers);
        if (Number.isFinite(position.accuracy) && position.accuracy > 0 && position.accuracy < 2000000) {
          L.circle(point, { radius: position.accuracy, color: "#d06724", weight: 1,
            dashArray: "4 4", fillOpacity: 0.04 }).bindTooltip("定位精度估计，非签到范围").addTo(this.layers);
        }
        bounds.extend(point);
      }
      this.map.fitBounds(bounds, { padding: [28, 28], maxZoom: 18, animate: false });
      if (!this.tiles) this.startTiles();
    }

    startTiles() {
      this.root.dataset.loadState = "loading";
      this.status.textContent = "正在加载地图…";
      const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, keepBuffer: 0, updateWhenIdle: true,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'
      });
      this.tiles = tiles;
      const fail = () => {
        if (this.tiles !== tiles) return;
        this.failed = true;
        this.showMessage("地图加载失败或超时，请检查网络后重试；签到不受影响。", true);
      };
      const startTimer = () => {
        clearTimeout(this.tileTimer);
        this.tileTimer = setTimeout(fail, 8000);
      };
      tiles.on("loading", startTimer);
      tiles.on("tileerror", () => setTimeout(fail, 0));
      tiles.on("load", () => {
        if (this.tiles !== tiles) return;
        clearTimeout(this.tileTimer);
        this.root.dataset.loadState = "ready";
        this.status.textContent = "可拖动地图或使用右上角按钮缩放。";
      });
      startTimer();
      tiles.addTo(this.map);
    }
  }

  document.querySelectorAll(".fence-map").forEach((root) => new FenceMap(root));
  const recordSelect = document.getElementById("record-map-select");
  if (recordSelect) {
    recordSelect.addEventListener("change", () => {
      const root = recordSelect.closest(".result-map-panel").querySelector(".fence-map");
      const option = recordSelect.selectedOptions[0];
      root.open = true;
      if (option.value) {
        root.dispatchEvent(new CustomEvent("attendance:position", { detail: {
          latitude: number(option.dataset.latitude), longitude: number(option.dataset.longitude),
          distance: number(option.dataset.distance), record: true
        } }));
      } else root.dispatchEvent(new CustomEvent("attendance:clear-position"));
    });
  }
})();
