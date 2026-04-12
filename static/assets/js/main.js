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
  const notification = document.getElementById('notification');
  const flashContainer = document.getElementById('flash-container'); // Контейнер для flash-сообщений
  let notificationTimeout = null;
  let notificationExitTimeout = null;

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
      // Делаем запрос на сервер для генерации новой капчи
      fetch('/refresh_captcha').catch((error) => {
        console.error('Ошибка обновления капчи:', error);
      });
    });
  }

  // Функция для отображения уведомлений
  function showNotification(message, type = 'info') {
    if (!notification) {
      return;
    }

    const isError = type === 'error';
    notification.setAttribute('role', isError ? 'alert' : 'status');
    notification.setAttribute('aria-live', isError ? 'assertive' : 'polite');
    notification.setAttribute('aria-atomic', 'true');
    notification.textContent = message;
    notification.className = `notification notification-${type}`;
    notification.classList.remove('notification-exit');
    if (notificationExitTimeout) {
      clearTimeout(notificationExitTimeout);
      notificationExitTimeout = null;
    }
    if (notificationTimeout) {
      clearTimeout(notificationTimeout);
      notificationTimeout = null;
    }
    notification.style.display = 'block';

    notificationTimeout = setTimeout(() => {
      notification.classList.add('notification-exit');
      notificationExitTimeout = setTimeout(() => {
        notification.classList.remove('notification-exit');
        notification.style.display = 'none';
      }, 180);
    }, 2800);

  }

  // Проверяем наличие сообщений flash
  const flashNode = document.getElementById('flash-messages');
  const flashMessages = JSON.parse(
    (flashNode && flashNode.textContent) || '[]',
  );
  flashMessages.forEach(([category, message]) => {
    showNotification(message, category);
  });

  // Автоматическое скрытие flash-сообщений
  if (flashContainer) {
    setTimeout(() => {
      flashContainer.style.display = 'none';
    }, 3000); // Скрыть через 3 секунды
  }
});
