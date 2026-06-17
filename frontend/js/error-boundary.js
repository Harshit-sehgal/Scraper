/* ═══════════════════════════════════════════
   DataForge — Error Boundary & Loading States
   ═══════════════════════════════════════════
   Provides error handling, loading indicators, and retry logic
   for improved frontend UX.
   ═══════════════════════════════════════════ */

// ─── Error Boundary ───
export class ErrorBoundary {
  constructor(options = {}) {
    this.onError = options.onError || console.error;
    this.onRetry = options.onRetry || null;
    this.maxRetries = options.maxRetries || 3;
    this.retryCount = 0;
    this.state = "idle"; // idle | loading | error | success
  }

  async execute(fn, context = {}) {
    this.state = "loading";
    this.showLoading(context.loadingElement);

    try {
      const result = await fn();
      this.state = "success";
      this.hideLoading(context.loadingElement);
      this.hideError(context.errorElement);
      this.retryCount = 0;
      return result;
    } catch (error) {
      this.state = "error";
      this.hideLoading(context.loadingElement);
      this.showError(error, context.errorElement);
      this.onError(error, context);
      throw error;
    }
  }

  showError(error, element) {
    if (!element) return;

    const message = error.message || "An unexpected error occurred";
    const errorBoundary = document.createElement("div");
    errorBoundary.className = "error-boundary";
    errorBoundary.setAttribute("role", "alert");

    const iconDiv = document.createElement("div");
    iconDiv.className = "error-icon";
    iconDiv.textContent = "⚠️";

    const msgDiv = document.createElement("div");
    msgDiv.className = "error-message";
    msgDiv.textContent = message;

    const actionsDiv = document.createElement("div");
    actionsDiv.className = "error-actions";

    const retryBtn = document.createElement("button");
    retryBtn.className = "error-retry-btn";
    retryBtn.textContent = `Retry${this.retryCount > 0 ? ` (${this.retryCount}/${this.maxRetries})` : ""}`;
    retryBtn.addEventListener("click", () => this.retry());

    const dismissBtn = document.createElement("button");
    dismissBtn.className = "error-dismiss-btn";
    dismissBtn.textContent = "Dismiss";
    dismissBtn.addEventListener("click", () => this.dismiss());

    actionsDiv.appendChild(retryBtn);
    actionsDiv.appendChild(dismissBtn);

    errorBoundary.appendChild(iconDiv);
    errorBoundary.appendChild(msgDiv);
    errorBoundary.appendChild(actionsDiv);

    element.appendChild(errorBoundary);
    element.style.display = "block";
  }

  hideError(element) {
    if (element) {
      element.style.display = "none";
    }
  }

  showLoading(element) {
    if (!element) return;

    element.innerHTML = `
      <div class="loading-indicator" aria-busy="true" aria-live="polite">
        <div class="loading-spinner"></div>
        <div class="loading-text">Loading...</div>
      </div>
    `;
    element.style.display = "block";
  }

  hideLoading(element) {
    if (element) {
      element.style.display = "none";
    }
  }

  escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  canRetry() {
    return this.retryCount < this.maxRetries;
  }

  incrementRetry() {
    this.retryCount++;
  }

  reset() {
    this.retryCount = 0;
    this.state = "idle";
  }
}

// ─── Loading States Manager ───
export class LoadingStates {
  constructor() {
    this.loadingStates = new Map();
    this.observers = new Map();
  }

  setLoading(key, isLoading, message = "Loading...") {
    this.loadingStates.set(key, { isLoading, message });
    this.notifyObservers(key, isLoading, message);
  }

  isLoading(key) {
    const state = this.loadingStates.get(key);
    return state ? state.isLoading : false;
  }

  getMessage(key) {
    const state = this.loadingStates.get(key);
    return state ? state.message : "";
  }

  observe(key, callback) {
    if (!this.observers.has(key)) {
      this.observers.set(key, []);
    }
    this.observers.get(key).push(callback);
  }

  notifyObservers(key, isLoading, message) {
    const observers = this.observers.get(key) || [];
    observers.forEach((callback) => callback(isLoading, message));
  }

  getGlobalLoadingState() {
    for (const [key, state] of this.loadingStates) {
      if (state.isLoading) {
        return { key, ...state };
      }
    }
    return null;
  }
}

// ─── Retry Logic ───
export class RetryHandler {
  constructor(options = {}) {
    this.maxRetries = options.maxRetries || 3;
    this.baseDelay = options.baseDelay || 1000;
    this.maxDelay = options.maxDelay || 10000;
    this.exponentialBase = options.exponentialBase || 2;
  }

  async executeWithRetry(fn, options = {}) {
    const { onRetry, shouldRetry = () => true } = options;
    let lastError;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        return await fn();
      } catch (error) {
        lastError = error;

        if (attempt < this.maxRetries && shouldRetry(error)) {
          const delay = this.calculateDelay(attempt);
          if (onRetry) {
            onRetry(error, attempt + 1, delay);
          }
          await this.sleep(delay);
        }
      }
    }

    throw lastError;
  }

  calculateDelay(attempt) {
    const delay = this.baseDelay * Math.pow(this.exponentialBase, attempt);
    return Math.min(delay, this.maxDelay);
  }

  sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

// ─── Toast Notifications ───
export class ToastManager {
  constructor() {
    this.container = null;
    this.init();
  }

  init() {
    if (typeof document === "undefined") return;

    this.container = document.createElement("div");
    this.container.id = "toast-container";
    this.container.className = "toast-container";
    this.container.setAttribute("aria-live", "polite");
    document.body.appendChild(this.container);
  }

  show(message, type = "info", duration = 3000) {
    if (!this.container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.setAttribute("role", "alert");

    const content = document.createElement("div");
    content.className = "toast-content";

    const iconSpan = document.createElement("span");
    iconSpan.className = "toast-icon";
    iconSpan.textContent = this.getIcon(type);

    const msgSpan = document.createElement("span");
    msgSpan.className = "toast-message";
    msgSpan.textContent = this.escapeHtml(message);

    content.appendChild(iconSpan);
    content.appendChild(msgSpan);

    const closeBtn = document.createElement("button");
    closeBtn.className = "toast-close";
    closeBtn.setAttribute("aria-label", "Close");
    closeBtn.textContent = "×";
    closeBtn.addEventListener("click", () => toast.remove());

    toast.appendChild(content);
    toast.appendChild(closeBtn);

    this.container.appendChild(toast);

    // Auto-remove after duration
    if (duration > 0) {
      setTimeout(() => {
        if (toast.parentElement) {
          toast.remove();
        }
      }, duration);
    }
  }

  getIcon(type) {
    const icons = {
      success: "✓",
      error: "✕",
      warning: "⚠",
      info: "ℹ",
    };
    return icons[type] || icons.info;
  }

  success(message, duration) {
    this.show(message, "success", duration);
  }

  error(message, duration) {
    this.show(message, "error", duration);
  }

  warning(message, duration) {
    this.show(message, "warning", duration);
  }

  info(message, duration) {
    this.show(message, "info", duration);
  }
}

// ─── Utility Functions ───
export function withErrorBoundary(fn, errorElement) {
  return async (...args) => {
    try {
      return await fn(...args);
    } catch (error) {
      errorBoundary.showError(error, errorElement);
      throw error;
    }
  };
}

export function withLoading(key, fn, loadingElement, errorElement) {
  return async (...args) => {
    loadingStates.setLoading(key, true);
    try {
      const result = await fn(...args);
      loadingStates.setLoading(key, false);
      return result;
    } catch (error) {
      loadingStates.setLoading(key, false);
      if (errorElement) {
        errorBoundary.showError(error, errorElement);
      }
      throw error;
    }
  };
}

export function createLoadingIndicator(message = "Loading...") {
  const div = document.createElement("div");
  div.className = "loading-indicator";
  div.setAttribute("aria-busy", "true");
  div.innerHTML = `
    <div class="loading-spinner"></div>
    <div class="loading-text">${message}</div>
  `;
  return div;
}

// ─── Skeleton Loading ───
export class SkeletonLoader {
  constructor() {
    this.skeletons = new Map();
  }

  createSkeleton(options = {}) {
    const {
      lines = 3,
      height = "1rem",
      width = "100%",
      borderRadius = "4px",
      className = "",
      ariaLabel = "Loading content",
    } = options;

    const container = document.createElement("div");
    container.className = `skeleton-container ${className}`;
    container.setAttribute("role", "status");
    container.setAttribute("aria-label", ariaLabel);
    container.setAttribute("aria-busy", "true");

    for (let i = 0; i < lines; i++) {
      const line = document.createElement("div");
      line.className = "skeleton-line";
      line.style.height = height;
      line.style.width = i === lines - 1 ? "60%" : width;
      line.style.borderRadius = borderRadius;
      container.appendChild(line);
    }

    return container;
  }

  createCardSkeleton() {
    return this.createSkeleton({
      lines: 4,
      height: "1rem",
      className: "skeleton-card",
    });
  }

  createTableSkeleton(rows = 5, cols = 4) {
    const container = document.createElement("div");
    container.className = "skeleton-table";
    container.setAttribute("role", "status");
    container.setAttribute("aria-label", "Loading table data");

    for (let i = 0; i < rows; i++) {
      const row = document.createElement("div");
      row.className = "skeleton-table-row";

      for (let j = 0; j < cols; j++) {
        const cell = document.createElement("div");
        cell.className = "skeleton-table-cell";
        cell.style.width = j === 0 ? "30%" : `${100 / cols}%`;
        row.appendChild(cell);
      }

      container.appendChild(row);
    }

    return container;
  }

  createListSkeleton(items = 5) {
    const container = document.createElement("div");
    container.className = "skeleton-list";
    container.setAttribute("role", "status");
    container.setAttribute("aria-label", "Loading list");

    for (let i = 0; i < items; i++) {
      const item = document.createElement("div");
      item.className = "skeleton-list-item";
      container.appendChild(item);
    }

    return container;
  }

  showSkeleton(element, skeletonType = "default", options = {}) {
    this.hideSkeleton(element);

    let skeleton;
    switch (skeletonType) {
      case "card":
        skeleton = this.createCardSkeleton();
        break;
      case "table":
        skeleton = this.createTableSkeleton(options.rows, options.cols);
        break;
      case "list":
        skeleton = this.createListSkeleton(options.items);
        break;
      default:
        skeleton = this.createSkeleton(options);
    }

    element.appendChild(skeleton);
    element.setAttribute("aria-busy", "true");
    this.skeletons.set(element, skeleton);
  }

  hideSkeleton(element) {
    const skeleton = this.skeletons.get(element);
    if (skeleton) {
      skeleton.remove();
      this.skeletons.delete(element);
      element.removeAttribute("aria-busy");
    }
  }

  replaceSkeletonWithData(element, dataElement) {
    this.hideSkeleton(element);
    element.appendChild(dataElement);
    element.setAttribute("aria-busy", "false");
  }
}

// ─── Global Instances ───
export const errorBoundary = new ErrorBoundary();
export const loadingStates = new LoadingStates();
export const retryHandler = new RetryHandler();
export const toast = new ToastManager();
export const skeletonLoader = new SkeletonLoader();
