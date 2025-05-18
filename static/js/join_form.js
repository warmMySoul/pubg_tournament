// Открытие модального окна с заявкой
window.openJoinClanModal = async function() {
    try {
        document.getElementById('joinClanModal').style.display = 'flex';
    } catch (error) {
        console.error('Error opening modal:', error);
    }
};

// Закрытие модального окна
window.closeJoinClanModal = function() {
    document.getElementById('joinClanModal').style.display = 'none';
};

// Обработчик отправки формы с автоматической проверкой авторизации
async function handleJoinClanSubmit(e) {
    e.preventDefault();
    const form = e.target;
    const submitButton = form.querySelector('button[type="submit"]');
    const originalText = submitButton.textContent;
    

    try {
        submitButton.disabled = true;
        submitButton.textContent = 'Отправка...';
        
        
        const formData = new FormData(form);

        // Если выбрана реклама, добавляем фиксированное значение
        if (document.getElementById('applicant_from').value === 'public') {
            formData.set('know_from_optional', 'Из рекламы');
        }

        const response = await fetch('/user/join-clan-request', {
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
            if (data.login_required) {
                openLoginModal();
                toastr.warning(data.message);
            } else {
                toastr.error(data.message || 'Ошибка при отправке заявки');
            }
            return;
        }

        toastr.success(data.message || 'Заявка успешно отправлена!');
        closeJoinClanModal();
        form.reset(); // Очищаем форму после успешной отправки
    } catch (error) {
        console.error('Submit error:', error);
        toastr.error('Произошла ошибка при отправке заявки');
    } finally {
        submitButton.disabled = false;
        submitButton.textContent = originalText;
    }
}

// Инициализация после загрузки DOM
document.addEventListener('DOMContentLoaded', function() {
    // Находим элементы
    const knowFromSelect = document.getElementById('applicant_from');
    const optionalField = document.getElementById('applicant_know_from_optional');
    
    // Скрываем поле по умолчанию, если выбрана реклама
    if (knowFromSelect.value === 'public') {
        optionalField.style.display = 'none';
        document.querySelector('label[for="applicant_know_from_optional"]').style.display = 'block';
        optionalField.value = 'Из рекламы';
    }
    
    // Добавляем обработчик изменения select
    knowFromSelect.addEventListener('change', toggleKnowFromField);

    // Обработчик формы
    document.getElementById('joinClanForm')?.addEventListener('submit', handleJoinClanSubmit);
    
    // Обработчик кнопки (теперь просто открывает форму)
    document.querySelector('.join_button')?.addEventListener('click', function(e) {
        e.preventDefault();
        openJoinClanModal();
    });
});

// Функция для управления видимостью дополнительного поля
function toggleKnowFromField() {
    const select = document.getElementById('applicant_from');
    const optionalField = document.getElementById('applicant_know_from_optional');
    const optionalLabel = document.querySelector('label[for="applicant_know_from_optional"]');
    
    if (select.value === 'public') {
        // Скрываем поле и устанавливаем значение
        optionalField.style.display = 'none';
        optionalLabel.style.display = 'none';
        optionalField.value = 'Из рекламы';
        optionalField.required = false;
    } else {
        // Показываем поле
        optionalField.style.display = 'block';
        optionalLabel.style.display = 'block';
        optionalField.value = '';
        optionalField.required = true;
        
        // Меняем текст label в зависимости от выбора
        if (select.value === 'friend') {
            optionalLabel.textContent = 'Ник друга/знакомого:';
        } else {
            optionalLabel.textContent = 'Укажите источник:';
        }
    }
}