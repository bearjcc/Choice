/* Modal shell: viewport-fixed layout, scroll lock, visualViewport (browser + tests). */

const ChoiceDialog = (function () {
  const NARROW_MQ = "(max-width: 699px)";
  const PAD = 12;

  let scrollY = 0;
  let vvDetach = null;
  let bodyObserver = null;

  function dialogEl() {
    return document.getElementById("dialog");
  }

  function shellEl() {
    const d = dialogEl();
    return d ? d.querySelector(".dialog-shell") : null;
  }

  function bodyEl() {
    return document.getElementById("dialog-body");
  }

  function safeInsets() {
    const probe = document.documentElement;
    const style = getComputedStyle(probe);
    const num = (name) => {
      const v = parseFloat(style.getPropertyValue(name));
      return Number.isFinite(v) ? v : 0;
    };
    return {
      top: num("--safe-top"),
      right: num("--safe-right"),
      bottom: num("--safe-bottom"),
      left: num("--safe-left"),
    };
  }

  function lockBody() {
    scrollY = window.scrollY || document.documentElement.scrollTop || 0;
    document.documentElement.classList.add("dialog-open");
    const body = document.body;
    body.style.position = "fixed";
    body.style.top = "-" + scrollY + "px";
    body.style.left = "0";
    body.style.right = "0";
    body.style.width = "100%";
  }

  function unlockBody() {
    document.documentElement.classList.remove("dialog-open");
    const body = document.body;
    body.style.position = "";
    body.style.top = "";
    body.style.left = "";
    body.style.right = "";
    body.style.width = "";
    window.scrollTo(0, scrollY);
  }

  function clearPosition() {
    const d = dialogEl();
    const shell = shellEl();
    if (!d) return;
    d.style.top = "";
    d.style.left = "";
    d.style.width = "";
    d.style.height = "";
    d.style.bottom = "";
    d.style.transform = "";
    if (shell) {
      shell.style.maxHeight = "";
      shell.style.maxWidth = "";
    }
  }

  function syncViewport() {
    const d = dialogEl();
    const shell = shellEl();
    if (!d || !d.open || !shell) return;

    const vv = window.visualViewport;
    const inset = safeInsets();
    const pad = PAD;
    const narrow = window.matchMedia(NARROW_MQ).matches;

    const vTop = vv ? vv.offsetTop : 0;
    const vLeft = vv ? vv.offsetLeft : 0;
    const vWidth = vv ? vv.width : window.innerWidth;
    const vHeight = vv ? vv.height : window.innerHeight;

    const maxW = Math.min(
      narrow ? vWidth : Math.min(32 * 16, vWidth),
      vWidth - pad * 2 - inset.left - inset.right,
    );
    const maxH = vHeight - pad * 2 - inset.top - inset.bottom;

    shell.style.maxWidth = Math.max(0, maxW) + "px";
    shell.style.maxHeight = Math.max(120, maxH) + "px";

    d.style.width = "max-content";
    d.style.maxWidth = "none";
    const placeShell = () => {
      const shellRect = shell.getBoundingClientRect();
      const boxW = shellRect.width;
      const boxH = shellRect.height;
      const minTop = vTop + inset.top + pad;
      const maxTop = vTop + vHeight - inset.bottom - pad - boxH;
      let top;
      if (narrow) {
        const bottomGap = vTop + vHeight - (inset.bottom + pad);
        top = bottomGap - boxH;
        if (top < minTop) top = minTop;
        const left = vLeft + (vWidth - boxW) / 2;
        d.style.left = Math.max(vLeft + inset.left + pad, left) + "px";
      } else {
        top = vTop + (vHeight - boxH) / 2;
        if (top < minTop) top = minTop;
        if (top > maxTop) top = maxTop;
        d.style.left = vLeft + (vWidth - boxW) / 2 + "px";
      }
      if (top > maxTop) top = maxTop;
      d.style.top = top + "px";
      d.style.bottom = "";
      d.style.transform = "";
    };
    placeShell();
    const fitted = shell.getBoundingClientRect();
    if (fitted.bottom > vTop + vHeight - inset.bottom - pad + 1) {
      const trim = fitted.bottom - (vTop + vHeight - inset.bottom - pad);
      const next = Math.max(120, maxH - trim);
      shell.style.maxHeight = next + "px";
      placeShell();
    }
  }

  function attachViewport() {
    syncViewport();
    const vv = window.visualViewport;
    if (!vv) return;
    const onChange = () => syncViewport();
    vv.addEventListener("resize", onChange);
    vv.addEventListener("scroll", onChange);
    window.addEventListener("resize", onChange);
    vvDetach = () => {
      vv.removeEventListener("resize", onChange);
      vv.removeEventListener("scroll", onChange);
      window.removeEventListener("resize", onChange);
      vvDetach = null;
    };
  }

  function detachViewport() {
    if (vvDetach) vvDetach();
    clearPosition();
  }

  function watchBody() {
    const body = bodyEl();
    if (!body || body.dataset.dialogWatch === "1") return;
    body.dataset.dialogWatch = "1";
    if (typeof ResizeObserver === "function") {
      bodyObserver = new ResizeObserver(() => syncViewport());
      bodyObserver.observe(body);
    }
  }

  function unwatchBody() {
    const body = bodyEl();
    if (bodyObserver) {
      bodyObserver.disconnect();
      bodyObserver = null;
    }
    if (body) delete body.dataset.dialogWatch;
  }

  function open() {
    const d = dialogEl();
    if (!d) return;
    if (!d.open) {
      d.showModal();
      lockBody();
      attachViewport();
      watchBody();
    }
    requestAnimationFrame(() => syncViewport());
  }

  function close() {
    const d = dialogEl();
    if (!d || !d.open) return;
    d.close();
  }

  function isOpen() {
    const d = dialogEl();
    return !!(d && d.open);
  }

  function init() {
    const d = dialogEl();
    if (!d || d.dataset.dialogUiInit === "1") return;
    d.dataset.dialogUiInit = "1";

    d.addEventListener("close", () => {
      unwatchBody();
      detachViewport();
      unlockBody();
      const body = bodyEl();
      if (body) body.replaceChildren();
    });

    d.addEventListener("click", (event) => {
      if (event.target === d) close();
    });

    d.addEventListener("cancel", (event) => {
      event.preventDefault();
      close();
    });
  }

  function confirm(message, options) {
    const opts = options || {};
    const title = opts.title != null ? opts.title : "Confirm";
    const okLabel = opts.confirmLabel != null ? opts.confirmLabel : "OK";
    const cancelLabel = opts.cancelLabel != null ? opts.cancelLabel : "Cancel";

    return new Promise((resolve) => {
      const body = bodyEl();
      if (!body) {
        resolve(false);
        return;
      }
      body.replaceChildren();
      const h = document.createElement("h2");
      h.textContent = title;
      body.append(h);
      const p = document.createElement("p");
      p.textContent = message;
      body.append(p);
      const row = document.createElement("div");
      row.className = "sheet-actions";
      const ok = document.createElement("button");
      ok.type = "button";
      ok.textContent = okLabel;
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.textContent = cancelLabel;
      const finish = (value) => {
        close();
        resolve(value);
      };
      ok.addEventListener("click", () => finish(true));
      cancel.addEventListener("click", () => finish(false));
      row.append(ok, cancel);
      body.append(row);
      open();
    });
  }

  /** Layout helper for headless tests: shell fits visual viewport box. */
  function layoutMetrics() {
    const shell = shellEl();
    const body = bodyEl();
    const vv = window.visualViewport;
    if (!shell || !vv) return null;
    const r = shell.getBoundingClientRect();
    const scrollEl = body || shell;
    return {
      top: r.top,
      left: r.left,
      right: r.right,
      bottom: r.bottom,
      width: r.width,
      height: r.height,
      vvTop: vv.offsetTop,
      vvLeft: vv.offsetLeft,
      vvRight: vv.offsetLeft + vv.width,
      vvBottom: vv.offsetTop + vv.height,
      scrollHeight: scrollEl.scrollHeight,
      clientHeight: scrollEl.clientHeight,
    };
  }

  return {
    init,
    open,
    close,
    isOpen,
    confirm,
    layoutMetrics,
    syncViewport,
  };
})();

if (typeof globalThis !== "undefined") {
  globalThis.ChoiceDialog = ChoiceDialog;
}
