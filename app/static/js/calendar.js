document.addEventListener('DOMContentLoaded', () => {
    const calendarDays = document.getElementById('calendarDays');
    const calendarTitle = document.getElementById('calendarTitle');
    const prevMonthBtn = document.getElementById('prevMonth');
    const nextMonthBtn = document.getElementById('nextMonth');

    if (!calendarDays) return;

    let currentDate = new Date();
    let newsDates = new Set();

    const months = [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ];

    async function fetchNewsDates() {
        try {
            const response = await fetch('/api/news-dates');
            if (response.ok) {
                const data = await response.json();
                const rawDates = Array.isArray(data) ? data : (data.dates || []);
                newsDates = new Set(rawDates.map(d => String(d).split('T')[0]));
                renderCalendar();
            }
        } catch (error) {
            console.error('Ошибка:', error);
            renderCalendar();
        }
    }

    function renderCalendar() {
        const year = currentDate.getFullYear();
        const month = currentDate.getMonth();

        if (calendarTitle) {
            calendarTitle.textContent = `${months[month]} ${year}`;
        }
        calendarDays.innerHTML = '';

        const firstDayIndex = (new Date(year, month, 1).getDay() + 6) % 7;
        const totalDays = new Date(year, month + 1, 0).getDate();
        const prevTotalDays = new Date(year, month, 0).getDate();

        for (let i = firstDayIndex; i > 0; i--) {
            const dayDiv = document.createElement('div');
            dayDiv.textContent = prevTotalDays - i + 1;
            dayDiv.style.color = '#cbd5e1';
            calendarDays.appendChild(dayDiv);
        }

        const today = new Date();
        for (let day = 1; day <= totalDays; day++) {
            const dayDiv = document.createElement('div');
            dayDiv.textContent = day;

            const formattedMonth = String(month + 1).padStart(2, '0');
            const formattedDay = String(day).padStart(2, '0');
            const dateStr = `${year}-${formattedMonth}-${formattedDay}`;

            if (day === today.getDate() && month === today.getMonth() && year === today.getFullYear()) {
                dayDiv.classList.add('today');
            }

            if (newsDates.has(dateStr)) {
                dayDiv.classList.add('has-news');
                dayDiv.title = 'Посмотреть новости за этот день';

                dayDiv.onclick = () => {
                    // Жестко берем только первые 10 символов даты (YYYY-MM-DD), отсекая любые двоеточия и мусор
                    const pureDate = String(dateStr).substring(0, 10);
                    window.location.href = `/all_news?date=${pureDate}`;
                };
            }

            calendarDays.appendChild(dayDiv);
        }

        const totalCells = firstDayIndex + totalDays;
        const remainingCells = (7 - (totalCells % 7)) % 7;
        for (let i = 1; i <= remainingCells; i++) {
            const dayDiv = document.createElement('div');
            dayDiv.textContent = i;
            dayDiv.style.color = '#cbd5e1';
            calendarDays.appendChild(dayDiv);
        }
    }

    if (prevMonthBtn) {
        prevMonthBtn.onclick = () => {
            currentDate.setMonth(currentDate.getMonth() - 1);
            renderCalendar();
        };
    }

    if (nextMonthBtn) {
        nextMonthBtn.onclick = () => {
            currentDate.setMonth(currentDate.getMonth() + 1);
            renderCalendar();
        };
    }

    fetchNewsDates();
});