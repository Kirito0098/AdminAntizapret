/*
 * CSP-совместимые делегированные обработчики.
 *
 * Заменяют inline-атрибуты on* (onsubmit/onclick/oninput/onchange), которые
 * блокируются строгой Content-Security-Policy (script-src без 'unsafe-inline').
 * Поведение 1:1 повторяет прежние inline-обработчики; разметка использует
 * data-* атрибуты вместо on*.
 */
(function () {
  "use strict";

  // <form data-confirm-submit="Текст?"> — подтверждение перед отправкой формы.
  document.addEventListener(
    "submit",
    function (e) {
      var form = e.target;
      if (form && form.getAttribute && form.getAttribute("data-confirm-submit")) {
        if (!window.confirm(form.getAttribute("data-confirm-submit"))) {
          e.preventDefault();
        }
      }
    },
    true
  );

  // <button data-confirm-click="Текст?"> — подтверждение по клику (отменяет click).
  document.addEventListener(
    "click",
    function (e) {
      var el = e.target.closest("[data-confirm-click]");
      if (el && !window.confirm(el.getAttribute("data-confirm-click"))) {
        e.preventDefault();
        e.stopPropagation();
      }
    },
    true
  );

  // Навигация (замена inline onclick window.open / window.location.href).
  document.addEventListener("click", function (e) {
    var openEl = e.target.closest("[data-open-url]");
    if (openEl) {
      e.preventDefault();
      window.open(openEl.getAttribute("data-open-url"), "_blank", "noopener");
      return;
    }
    var navEl = e.target.closest("[data-nav-url]");
    if (navEl) {
      e.preventDefault();
      window.location.href = navEl.getAttribute("data-nav-url");
    }
  });

  // <input data-sanitize="clientname|digits" data-sanitize-max="N"> — санитизация ввода.
  document.addEventListener("input", function (e) {
    var el = e.target;
    if (!el || !el.getAttribute || !el.getAttribute("data-sanitize")) {
      return;
    }
    var kind = el.getAttribute("data-sanitize");
    var max = parseInt(el.getAttribute("data-sanitize-max") || "0", 10);
    var value = el.value;
    if (kind === "clientname") {
      value = value.replace(/[^a-zA-Z0-9_-]/g, "");
    } else if (kind === "digits") {
      value = value.replace(/[^0-9]/g, "");
    }
    if (max > 0 && value.length > max) {
      value = value.slice(0, max);
    }
    if (value !== el.value) {
      el.value = value;
    }
  });

  // Чекбокс-тумблер с подтверждением и автосабмитом формы.
  //   data-toggle-confirm="Текст?"
  //   data-toggle-mode="off-confirm" — изначально включён; выключение требует подтверждения.
  //   data-toggle-mode="on-confirm"  — изначально выключен; включение требует подтверждения.
  document.addEventListener("change", function (e) {
    var el = e.target;
    if (!el || !el.getAttribute || !el.getAttribute("data-toggle-confirm")) {
      return;
    }
    var mode = el.getAttribute("data-toggle-mode") || "off-confirm";
    var msg = el.getAttribute("data-toggle-confirm");
    if (mode === "off-confirm") {
      if (!window.confirm(msg)) {
        el.checked = true;
        return;
      }
    } else if (mode === "on-confirm") {
      if (!el.checked) {
        return;
      }
      if (!window.confirm(msg)) {
        el.checked = false;
        return;
      }
    }
    if (el.form) {
      el.form.submit();
    }
  });
})();
