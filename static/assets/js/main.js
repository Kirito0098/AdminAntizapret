/*=============== SHOW HIDDEN - PASSWORD ===============*/
const showHiddenPass = (loginPass, loginEye) =>{
   const input = document.getElementById(loginPass),
         iconEye = document.getElementById(loginEye)

   iconEye.addEventListener('click', () =>{
      // Change password to text
      if(input.type === 'password'){
         // Switch to text
         input.type = 'text'

         // Icon change
         iconEye.classList.add('ri-eye-line')
         iconEye.classList.remove('ri-eye-off-line')
      } else{
         // Change to password
         input.type = 'password'

         // Icon change
         iconEye.classList.remove('ri-eye-line')
         iconEye.classList.add('ri-eye-off-line')
      }
   })
}

showHiddenPass('login-pass','login-eye')

document.addEventListener('DOMContentLoaded', function () {
    const notification = document.getElementById('notification');
    const flashContainer = document.getElementById('flash-container'); // Контейнер для flash-сообщений

    // Функция для отображения уведомлений
    function showNotification(message, type = 'info') {
        notification.textContent = message;
        notification.className = `notification notification-${type}`;
        notification.style.display = 'block';
        setTimeout(() => {
            notification.style.display = 'none';
        }, 3000);
    }

    // Проверяем наличие сообщений flash
    const flashMessages = JSON.parse(document.getElementById('flash-messages').textContent || '[]');
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