/*=============== SHOW HIDDEN - PASSWORD ===============*/
const showHiddenPass = (loginPass, loginEye) => {
  const input = document.getElementById(loginPass),
    iconEye = document.getElementById(loginEye);

  if (!input || !iconEye) {
    return;
  }

  iconEye.setAttribute('role', 'button');
  iconEye.setAttribute('tabindex', '0');
  iconEye.setAttribute('aria-label', 'Показать пароль');

  const togglePasswordVisibility = () => {
    const revealPassword = input.type === 'password';
    input.type = revealPassword ? 'text' : 'password';

    iconEye.classList.toggle('ri-eye-line', revealPassword);
    iconEye.classList.toggle('ri-eye-off-line', !revealPassword);
    iconEye.setAttribute('aria-label', revealPassword ? 'Скрыть пароль' : 'Показать пароль');
  };

  iconEye.addEventListener('click', togglePasswordVisibility);
  iconEye.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      togglePasswordVisibility();
    }
  });
};

showHiddenPass('login-pass', 'login-eye');

document.addEventListener('DOMContentLoaded', function () {
  // Включение капчи после 2 неудачных авторизаций
  const loginForm = document.querySelector('.login__form');
  const captchaContainer = document.querySelector('.captcha-container');
  const attempts = Number.parseInt(loginForm?.dataset?.attempts || '0', 10);
  if (captchaContainer && Number.isFinite(attempts) && attempts >= 2) {
    captchaContainer.classList.remove('hidden');
  }

  const loginSubmitButton = document.getElementById('login-submit');
  if (loginForm && loginSubmitButton) {
    loginForm.addEventListener('submit', function () {
      loginSubmitButton.disabled = true;
      loginSubmitButton.setAttribute('aria-busy', 'true');
      loginSubmitButton.dataset.defaultText = loginSubmitButton.textContent || 'Войти';
      loginSubmitButton.textContent = 'Входим...';
    });
  }

  // Обновление капчи
  const refreshButton = document.querySelector('#refresh-captcha');
  const captchaImg = document.querySelector('#captcha-img');
  if (refreshButton && captchaImg) {
    refreshButton.addEventListener('click', function () {
      captchaImg.src = '/captcha.png?' + new Date().getTime();
      fetch('/refresh_captcha').catch((error) => {
        console.error('Ошибка обновления капчи:', error);
      });
    });
  }

  const flashNode = document.getElementById('flash-messages');
  const normalizeType = window.normalizeNotificationType || ((category) => {
    const c = String(category || 'info').toLowerCase();
    if (['error', 'danger'].includes(c)) return 'error';
    if (['success', 'ok'].includes(c)) return 'success';
    if (['warning', 'warn'].includes(c)) return 'warning';
    return 'info';
  });

  let flashMessages = [];
  try {
    flashMessages = JSON.parse((flashNode && flashNode.textContent) || '[]');
  } catch (_e) {
    flashMessages = [];
  }

  if (typeof window.showNotification === 'function') {
    flashMessages.forEach(([category, message], index) => {
      if (!message) return;
      setTimeout(
        () => window.showNotification(message, normalizeType(category)),
        index * 150
      );
    });
  }
});
