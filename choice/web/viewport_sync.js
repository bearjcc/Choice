/* Shared visualViewport → CSS variables (--vv-top, --vv-h, …) for dialog + filter sheet. */

const ChoiceVisualViewport = (function () {
  const VARS = ["--vv-top", "--vv-left", "--vv-w", "--vv-h"];

  let refcount = 0;
  let removeListeners = null;
  const listeners = new Set();

  function readBox() {
    const vv = window.visualViewport;
    return {
      top: vv ? vv.offsetTop : 0,
      left: vv ? vv.offsetLeft : 0,
      width: vv ? vv.width : window.innerWidth,
      height: vv ? vv.height : window.innerHeight,
    };
  }

  function apply() {
    const box = readBox();
    const root = document.documentElement;
    root.style.setProperty("--vv-top", box.top + "px");
    root.style.setProperty("--vv-left", box.left + "px");
    root.style.setProperty("--vv-w", box.width + "px");
    root.style.setProperty("--vv-h", box.height + "px");
    listeners.forEach((fn) => {
      try {
        fn(box);
      } catch (_e) {
        /* ignore */
      }
    });
    return box;
  }

  function clear() {
    const root = document.documentElement;
    VARS.forEach((name) => root.style.removeProperty(name));
  }

  function bindListeners() {
    const onChange = () => apply();
    const vv = window.visualViewport;
    if (vv) {
      vv.addEventListener("resize", onChange);
      vv.addEventListener("scroll", onChange);
    }
    window.addEventListener("resize", onChange);
    return () => {
      if (vv) {
        vv.removeEventListener("resize", onChange);
        vv.removeEventListener("scroll", onChange);
      }
      window.removeEventListener("resize", onChange);
    };
  }

  /** Register listener; returns unsubscribe. Refcount keeps vars updated while any sheet/dialog is open. */
  function attach(onChange) {
    if (onChange) listeners.add(onChange);
    refcount += 1;
    if (refcount === 1) {
      apply();
      removeListeners = bindListeners();
    } else if (onChange) {
      onChange(readBox());
    }
    return () => detach(onChange);
  }

  function detach(onChange) {
    if (onChange) listeners.delete(onChange);
    refcount = Math.max(0, refcount - 1);
    if (refcount === 0) {
      if (removeListeners) {
        removeListeners();
        removeListeners = null;
      }
      clear();
      listeners.clear();
    }
  }

  return {
    readBox,
    apply,
    attach,
    detach,
  };
})();

if (typeof globalThis !== "undefined") {
  globalThis.ChoiceVisualViewport = ChoiceVisualViewport;
}
