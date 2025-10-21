// Функции управления модальными окнами

function openLoginModal() {
    document.getElementById('loginModal').style.display = 'flex';
    resetToLoginTab();
}

function closeLoginModal() {
    document.getElementById('loginModal').style.display = 'none';
}

function openForgotPasswordModal() {
    closeLoginModal();
    document.getElementById('forgotPasswordModal').style.display = 'flex';
}

function closeForgotPasswordModal() {
    document.getElementById('forgotPasswordModal').style.display = 'none';
}

function openResetPasswordModal() {
    document.getElementById('resetPasswordModal').style.display = 'flex';
}

function closeResetPasswordModal() {
    document.getElementById('resetPasswordModal').style.display = 'none';
}

function openVerifyModal() {
    document.getElementById('verifyEmailModal').style.display = 'flex';
}

function closeVerifyModal() {
    document.getElementById('verifyEmailModal').style.display = 'none';
}

// Сброс на вкладку авторизации
function resetToLoginTab() {
    document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.auth-tab-content').forEach(content => content.classList.remove('active'));
    
    document.querySelector('.tab-button[data-tab="login"]').classList.add('active');
    document.getElementById('login-tab').classList.add('active');
}

// Проверка URL на наличие параметра login_required=1
function checkLoginRequiredParam() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('login_required') === '1') {
        openLoginModal();
        
        // Убираем параметр из URL без перезагрузки страницы
        const newUrl = window.location.pathname + 
                      window.location.search.replace(/[?&]login_required=1(&|$)/, '') + 
                      window.location.hash;
        window.history.replaceState({}, document.title, newUrl);
    }
}

// Обработчик для кнопки "Войти"
document.getElementById('loginButton')?.addEventListener('click', function(e) {
    e.preventDefault();
    openLoginModal();
});

// Обработка переключения табов
document.querySelectorAll('.tab-button').forEach(button => {
    button.addEventListener('click', function() {
        document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.auth-tab-content').forEach(content => content.classList.remove('active'));
        
        this.classList.add('active');
        const tabId = this.getAttribute('data-tab') + '-tab';
        document.getElementById(tabId).classList.add('active');
    });
});

// Валидация логина
function validateUsername(prefix = '') {
    const usernameInput = document.getElementById(prefix + 'username');
    const usernameError = document.getElementById(prefix + 'usernameError');
    const regex = /^[a-zA-Z0-9_.]+$/;

    if (!regex.test(usernameInput.value)) {
        usernameError.style.display = 'flex';
        return false;
    }
    usernameError.style.display = 'none';
    return true;
}

// Валидация пароля
function validatePassword(prefix = '') {
    const password = document.getElementById(prefix + 'password').value;
    const lengthReq = document.getElementById(prefix + 'lengthReq');
    const charsReq = document.getElementById(prefix + 'charsReq');
    const upperReq = document.getElementById(prefix + 'upperReq');

    if (password.length === 0) {
        lengthReq.style.color = '';
        charsReq.style.color = '';
        upperReq.style.color = '';
        return false;
    }

    let allValid = true;

    if (password.length >= 6 && password.length <= 30) {
        lengthReq.style.color = 'green';
    } else {
        lengthReq.style.color = 'red';
        allValid = false;
    }

    const charsRegex = /^[a-zA-Z0-9_!.,]*$/;
    if (charsRegex.test(password)) {
        charsReq.style.color = 'green';
    } else {
        charsReq.style.color = 'red';
        allValid = false;
    }

    if (/[A-Z]/.test(password)) {
        upperReq.style.color = 'green';
    } else {
        upperReq.style.color = 'red';
        allValid = false;
    }

    return allValid;
}

// Общая валидация формы регистрации
function validateRegisterForm() {
    return validateUsername('reg_') && validatePassword('reg_');
}

// Валидация пароля при сбросе
function validateResetPassword() {
    const password = document.getElementById('new_password').value;
    const lengthReq = document.getElementById('reset_lengthReq');
    const charsReq = document.getElementById('reset_charsReq');
    const upperReq = document.getElementById('reset_upperReq');

    if (password.length === 0) {
        lengthReq.style.color = '';
        charsReq.style.color = '';
        upperReq.style.color = '';
        return false;
    }

    let allValid = true;

    if (password.length >= 6 && password.length <= 30) {
        lengthReq.style.color = 'green';
    } else {
        lengthReq.style.color = 'red';
        allValid = false;
    }

    const charsRegex = /^[a-zA-Z0-9_!.,]*$/;
    if (charsRegex.test(password)) {
        charsReq.style.color = 'green';
    } else {
        charsReq.style.color = 'red';
        allValid = false;
    }

    if (/[A-Z]/.test(password)) {
        upperReq.style.color = 'green';
    } else {
        upperReq.style.color = 'red';
        allValid = false;
    }

    return allValid;
}

// Обработчики отправки форм
async function handleFormSubmit(e, url, successCallback) {
    e.preventDefault();
    const form = e.target;
    const submitButton = form.querySelector('button[type="submit"]');
    const originalText = submitButton.textContent;

    try {
        submitButton.disabled = true;
        submitButton.textContent = 'Отправка...';
        
        const formData = new FormData(form);
        const response = await fetch(url, {
            method: 'POST',
            body: formData,
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'include'
        });

        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || 'Ошибка сервера');
        }

        if (typeof successCallback === 'function') {
            successCallback(data);
        } else {
            toastr.success(data.message || 'Успешно');
            if (data.redirect) {
                window.location.href = data.redirect;
            }
        }
    } catch (error) {
        console.error('Form submit error:', error);
        toastr.error(error.message || 'Произошла ошибка');
    } finally {
        submitButton.disabled = false;
        submitButton.textContent = originalText;
    }
}

// Обработка отправки формы авторизации
async function handleLoginSubmit(e) {
    await handleFormSubmit(e, '/user/login', (data) => {
        toastr.success(data.message);
        closeLoginModal();
        if (data.redirect) {
            window.location.href = data.redirect;
        } else {
            window.location.reload();
        }
    });
}

// Обработка отправки формы регистрации
async function handleRegisterSubmit(e) {
    if (!validateRegisterForm()) {
        toastr.error('Пожалуйста, исправьте ошибки в форме');
        return;
    }
    await handleFormSubmit(e, '/user/register', (data) => {
        closeLoginModal();
        openVerifyModal();
    });
}

// Обработка отправки кода подтверждения
async function handleVerifySubmit(e) {
    await handleFormSubmit(e, '/user/verify-email', (data) => {
        toastr.success(data.message || 'Введен правильный код!');
        closeVerifyModal();
        window.location.href = data.redirect || '/';
    });
}

// Обработка отправки формы восстановления пароля
async function handleForgotPasswordSubmit(e) {
    await handleFormSubmit(e, '/user/forgot-password', (data) => {
        toastr.success(data.message || 'Код подтверждения отправлен на вашу почту');
        closeForgotPasswordModal();
        openResetPasswordModal();
    });
}

// Обработка отправки формы сброса пароля
async function handleResetPasswordSubmit(e) {
    await handleFormSubmit(e, '/user/reset-password', (data) => {
        toastr.success(data.message || 'Пароль успешно изменён');
        closeResetPasswordModal();
        openLoginModal();
    });
}

// Функция для повторной отправки кода
async function resendVerificationCode() {
    try {
        const response = await fetch('/user/resend-code', {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'include'
        });

        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || 'Ошибка сервера');
        }

        toastr.success(data.message || 'Новый код отправлен на ваш email');
    } catch (error) {
        console.error('Resend code error:', error);
        toastr.error(error.message || 'Произошла ошибка при отправке кода');
    }
}

// Инициализация
document.addEventListener('DOMContentLoaded', function() {
    // Проверяем параметр login_required при загрузке страницы
    checkLoginRequiredParam();

    // Валидация
    document.getElementById('reg_username')?.addEventListener('input', () => validateUsername('reg_'));
    document.getElementById('reg_password')?.addEventListener('input', () => validatePassword('reg_'));
    document.getElementById('new_password')?.addEventListener('input', validateResetPassword);

    // Обработчики форм
    document.getElementById('loginForm')?.addEventListener('submit', handleLoginSubmit);
    document.getElementById('registerForm')?.addEventListener('submit', handleRegisterSubmit);
    document.getElementById('verifyEmailForm')?.addEventListener('submit', handleVerifySubmit);
    document.getElementById('forgotPasswordForm')?.addEventListener('submit', handleForgotPasswordSubmit);
    document.getElementById('resetPasswordForm')?.addEventListener('submit', handleResetPasswordSubmit);

    // Ссылка "Забыли пароль?"
    document.querySelector('.forgot-password-link a')?.addEventListener('click', function(e) {
        e.preventDefault();
        openForgotPasswordModal();
    });

    // Закрытие модальных окон
    document.querySelectorAll('.modal_container .btn-close').forEach(closeBtn => {
        closeBtn.addEventListener('click', function() {
            this.closest('.modal_container').style.display = 'none';
        });
    });

    // Закрытие при клике вне модального окна
    /*
    document.querySelectorAll('.modal_container').forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                this.style.display = 'none';
            }
        });
    });
    */
});