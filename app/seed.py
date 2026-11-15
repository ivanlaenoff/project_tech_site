# -*- coding: utf-8 -*-
"""
Стартовые данные: группы, расписание, аккаунты, оценки, документы.

Запускается при старте приложения (idempotent — повторный запуск ничего
не дублирует и не ломает).
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

import app.models as models
from app.auth import hash_password
from app.database import SessionLocal

# ======================================================================
# Справочники
# ======================================================================

WEEKDAYS = {
    1: "Понедельник",
    2: "Вторник",
    3: "Среда",
    4: "Четверг",
    5: "Пятница",
    6: "Суббота",
}

LESSON_TIMES = {
    1: "08:30 — 10:00",
    2: "10:10 — 11:40",
    3: "12:10 — 13:40",
    4: "13:50 — 15:20",
    5: "15:30 — 17:00",
}

GROUPS = [
    # (название, specialty_id, курс, куратор)
    ("ИС-21", "info", 3, "Иванова М. И."),
    ("ИС-22", "info", 2, "Иванова М. И."),
    ("ИС-23", "info", 1, "Петров С. В."),
    ("БД-21", "bank", 3, "Кузнецова О. Н."),
    ("БД-23", "bank", 1, "Кузнецова О. Н."),
    ("ЭК-22", "accounting", 2, "Петров С. В."),
    ("ФН-23", "finance", 1, "Петров С. В."),
    ("ЮР-21", "law", 3, "Сидорова А. П."),
    ("КМ-22", "commerce", 2, "Смирнова Е. В."),
    ("ТВ-23", "goods", 1, "Смирнова Е. В."),
    ("ПК-21", "cook", 3, "Морозов А. В."),
]

TEACHERS = [
    # (email, пароль, фамилия, имя, отчество, должность, предмет)
    ("teacher@tkt33.ru", "teacher123", "Иванова", "Мария", "Ивановна",
     "Преподаватель информатики", "Информационные системы"),
    ("petrov@tkt33.ru", "teacher123", "Петров", "Сергей", "Владимирович",
     "Преподаватель экономических дисциплин", "Экономика"),
    ("sidorova@tkt33.ru", "teacher123", "Сидорова", "Анна", "Петровна",
     "Преподаватель правовых дисциплин", "Право"),
    ("kuznetsova@tkt33.ru", "teacher123", "Кузнецова", "Ольга", "Николаевна",
     "Преподаватель банковского дела", "Банковское дело"),
    ("morozov@tkt33.ru", "teacher123", "Морозов", "Алексей", "Викторович",
     "Мастер производственного обучения", "Технология приготовления пищи"),
]

# Предметы по специальностям (для генерации расписания)
SUBJECTS_BY_SPECIALTY = {
    "info": [
        "Информационные технологии", "Программирование на Python", "Веб-разработка",
        "Базы данных", "Компьютерные сети", "Тестирование ПО", "Математика",
        "Инженерная графика", "Охрана труда", "Физическая культура",
    ],
    "bank": [
        "Банковское дело", "Организация кредитной работы", "Расчёты и платежи",
        "Финансовая грамотность", "Бухгалтерский учёт в банках", "Экономика организации",
        "Математика", "Информационные технологии", "Физическая культура",
    ],
    "accounting": [
        "Бухгалтерский учёт", "Налоги и налогообложение", "Анализ финансовой отчётности",
        "1С: Бухгалтерия", "Аудит", "Экономика организации", "Математика",
        "Документационное обеспечение", "Физическая культура",
    ],
    "finance": [
        "Финансы и кредит", "Бюджетирование", "Финансовый анализ", "Страхование",
        "Рынок ценных бумаг", "Налоги", "Математика", "Информационные технологии",
        "Физическая культура",
    ],
    "law": [
        "Гражданское право", "Уголовное право", "Трудовое право", "Конституционное право",
        "Административное право", "Делопроизводство", "Русский язык и культура речи",
        "Обществознание", "История", "Физическая культура",
    ],
    "commerce": [
        "Коммерческая деятельность", "Маркетинг", "Мерчандайзинг", "Логистика",
        "Товароведение", "Деловые коммуникации", "Экономика", "Информационные технологии",
        "Физическая культура",
    ],
    "goods": [
        "Товароведение продовольственных товаров", "Товароведение непродовольственных товаров",
        "Экспертиза качества", "Стандартизация и сертификация", "Метрология",
        "Химия", "Физика", "Информационные технологии", "Физическая культура",
    ],
    "cook": [
        "Технология приготовления пищи", "Кондитерское мастерство", "Кулинарное мастерство",
        "Санитария и гигиена", "Организация производства", "Калькуляция и учёт",
        "Товароведение пищевых продуктов", "Физическая культура",
    ],
}

ROOMS = ["101", "102", "105", "108", "112", "201", "203", "205", "210",
         "212", "215", "Лаборатория ИТ", "Спортзал", "Мастерская"]

LESSON_TYPES = ["Лекция", "Практика", "Лабораторная"]


# ======================================================================
# Генерация расписания
# ======================================================================

def _pick(seq, *keys):
    """Стабильный «псевдослучайный» выбор из списка."""
    h = 0
    for k in keys:
        h = (h * 131 + int(k)) % 1000003
    return seq[h % len(seq)]


def build_schedule(group_name, specialty_id, course):
    """Список пар для группы (dict-строки для моделей Schedule)."""
    subjects = SUBJECTS_BY_SPECIALTY.get(specialty_id, SUBJECTS_BY_SPECIALTY["info"])
    rows = []
    for weekday in range(1, 7):
        max_lessons = 3 if weekday == 6 else 5
        if weekday == 5 and course == 1:
            max_lessons = 4
        for lesson_no in range(1, max_lessons + 1):
            subject = _pick(subjects, weekday, lesson_no, course, len(group_name))
            teacher = _pick([t[2] + " " + t[3][0] + "." + t[4][0] + "." for t in TEACHERS],
                            weekday, lesson_no, course)
            room = _pick(ROOMS, weekday, lesson_no, len(group_name))
            lesson_type = LESSON_TYPES[(weekday + lesson_no + course) % len(LESSON_TYPES)]
            rows.append({
                "weekday": weekday,
                "lesson_no": lesson_no,
                "subject": subject,
                "teacher_name": teacher,
                "room": room,
                "lesson_type": lesson_type,
            })
    return rows


# ======================================================================
# Документы
# ======================================================================

DOCUMENTS = [
    ("Устав АНПОО КТТО", "Основные сведения",
     "Учредительный документ организации в действующей редакции."),
    ("Лицензия на образовательную деятельность", "Основные сведения",
     "№ 68Л01 № 0000598 от 15.02.2016, бессрочно, регистрационный номер 19/26."),
    ("Свидетельство о государственной аккредитации", "Основные сведения",
     "№ А007-01289-68/01149434 от 15.03.2019, бессрочно."),
    ("Правила внутреннего распорядка обучающихся", "Локальные акты",
     "Режим занятий, права и обязанности студентов."),
    ("Положение о текущем контроле и промежуточной аттестации", "Локальные акты",
     "Порядок проведения зачётов и экзаменов."),
    ("Положение о стипендиях и мерах поддержки", "Локальные акты",
     "Виды стипендий, условия назначения и размеры выплат."),
    ("Положение о практике", "Образование",
     "Порядок организации учебной и производственной практики."),
    ("Образовательные программы по специальностям", "Образование",
     "Аннотации рабочих программ и учебные планы."),
    ("Отчёт о результатах самообследования", "Образование",
     "Ежегодный аналитический отчёт организации."),
    ("План приёма на 2026/2027 учебный год", "Приём",
     "Количество бюджетных и платных мест по специальностям."),
    ("Правила приёма и порядок зачисления", "Приём",
     "Сроки, перечень документов и процедура конкурса."),
    ("Положение об оплате обучения", "Финансы",
     "Стоимость обучения и порядок заключения договоров."),
]


# ======================================================================
# Инициализация
# ======================================================================

def _ensure_columns():
    """
    Аккуратные миграции для уже существующей базы: create_all не добавляет
    колонки в существующие таблицы, поэтому досоздаём недостающие вручную.
    """
    from sqlalchemy import text
    from app.database import engine

    with engine.begin() as conn:
        tables = [row[0] for row in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'"))]
        if "teacher_profiles" in tables:
            cols = [row[1] for row in conn.execute(
                text("PRAGMA table_info(teacher_profiles)"))]
            if "middle_name" not in cols:
                conn.execute(text(
                    "ALTER TABLE teacher_profiles ADD COLUMN middle_name VARCHAR"))


def ensure_seed_data():
    db: Session = SessionLocal()
    try:
        _ensure_columns()

        # ---- группы ----
        groups_map = {}
        for name, spec, course, curator in GROUPS:
            group = db.query(models.Group).filter(models.Group.name == name).first()
            if not group:
                group = models.Group(name=name, specialty_id=spec, course=course,
                                     curator=curator, students_count=20 + course * 2)
                db.add(group)
                db.flush()
            groups_map[name] = group
        db.commit()

        # ---- расписание ----
        if db.query(models.Schedule).count() == 0:
            for name, spec, course, _ in GROUPS:
                group = groups_map[name]
                for row in build_schedule(name, spec, course):
                    db.add(models.Schedule(group_id=group.id, **row))
            db.commit()

        # ---- администратор ----
        if not db.query(models.User).filter(models.User.email == "admin@tkt33.ru").first():
            db.add(models.User(
                email="admin@tkt33.ru",
                password_hash=hash_password("admin123"),
                role=models.UserRole.ADMIN.value,
            ))
            db.commit()

        # ---- преподаватели ----
        for email, password, last, first, middle, position, subject in TEACHERS:
            user = db.query(models.User).filter(models.User.email == email).first()
            if not user:
                user = models.User(
                    email=email,
                    password_hash=hash_password(password),
                    role=models.UserRole.TEACHER.value,
                )
                db.add(user)
                db.flush()
                db.add(models.TeacherProfile(
                    user_id=user.id,
                    first_name=first,
                    last_name=last,
                    middle_name=middle,
                    phone="+7 (4752) 53-65-6" + str(len(last) % 10),
                    position=position,
                    subject=subject,
                ))
            else:
                # заполняем отчество у профилей, созданных до появления колонки
                profile = db.query(models.TeacherProfile).filter(
                    models.TeacherProfile.user_id == user.id).first()
                if profile and not profile.middle_name:
                    profile.middle_name = middle
        db.commit()

        # ---- студенты ----
        demo_students = [
            ("student@tkt33.ru", "student123", "Смирнов", "Иван", "ИС-21", "21-ИС-001"),
            ("student2@tkt33.ru", "student123", "Кузнецов", "Артём", "ИС-21", "21-ИС-002"),
            ("student3@tkt33.ru", "student123", "Морозова", "Дарья", "ИС-21", "21-ИС-003"),
            ("student4@tkt33.ru", "student123", "Волков", "Никита", "ИС-21", "21-ИС-004"),
            ("student5@tkt33.ru", "student123", "Соколова", "Полина", "ИС-21", "21-ИС-005"),
            ("student6@tkt33.ru", "student123", "Лебедев", "Максим", "БД-21", "21-БД-001"),
        ]
        for email, password, last, first, group_name, record_book in demo_students:
            user = db.query(models.User).filter(models.User.email == email).first()
            if not user:
                user = models.User(
                    email=email,
                    password_hash=hash_password(password),
                    role=models.UserRole.STUDENT.value,
                )
                db.add(user)
                db.flush()
                group = groups_map.get(group_name)
                db.add(models.StudentProfile(
                    user_id=user.id,
                    first_name=first,
                    last_name=last,
                    phone="+7 (900) 000-00-0" + str(len(first) % 10),
                    group_name=group_name,
                    group_id=group.id if group else None,
                    record_book=record_book,
                ))
        db.commit()

        # ---- оценки демо-студента ----
        student = db.query(models.User).filter(models.User.email == "student@tkt33.ru").first()
        if student and db.query(models.Grade).filter(models.Grade.user_id == student.id).count() == 0:
            plan = [
                ("Информационные технологии", 5, "2026-09-12"),
                ("Информационные технологии", 5, "2026-10-03"),
                ("Программирование на Python", 4, "2026-09-19"),
                ("Программирование на Python", 5, "2026-10-10"),
                ("Веб-разработка", 4, "2026-09-26"),
                ("Веб-разработка", 5, "2026-10-17"),
                ("Базы данных", 4, "2026-10-08"),
                ("Базы данных", 4, "2026-11-07"),
                ("Компьютерные сети", 3, "2026-10-22"),
                ("Математика", 4, "2026-09-15"),
                ("Математика", 5, "2026-11-05"),
                ("Тестирование ПО", 5, "2026-11-12"),
                ("Физическая культура", 5, "2026-09-29"),
            ]
            for subject, mark, d in plan:
                db.add(models.Grade(
                    user_id=student.id,
                    subject=subject,
                    mark=mark,
                    date=d,
                    teacher_name="Иванова М. И." if "Информац" in subject or "Про" in subject
                    else "Петров С. В.",
                    comment="Работа на занятии" if mark >= 4 else "Требуется доработка",
                ))
            db.commit()

        # ---- домашние задания ----
        is21 = groups_map.get("ИС-21")
        if is21 and db.query(models.Homework).filter(models.Homework.group_id == is21.id).count() == 0:
            today = date.today()
            tasks = [
                ("Программирование на Python", "Реализовать классы для задачи «Библиотека», "
                 "сдать до пятницы в репозиторий.", 2),
                ("Веб-разработка", "Свёрстать адаптивную карточку товара, приложить скриншоты.", 3),
                ("Базы данных", "Составить ER-диаграмму для интернет-магазина.", 4),
                ("Информационные технологии", "Подготовить доклад по теме «Облачные сервисы».", 5),
            ]
            for subject, task, days in tasks:
                db.add(models.Homework(
                    group_id=is21.id,
                    subject=subject,
                    task=task,
                    due_date=(today + timedelta(days=days)).strftime("%Y-%m-%d"),
                    teacher_name="Иванова М. И.",
                ))
            db.commit()

        # ---- документы ----
        if db.query(models.DocumentFile).count() == 0:
            for i, (title, category, description) in enumerate(DOCUMENTS):
                db.add(models.DocumentFile(
                    title=title,
                    category=category,
                    description=description,
                    order=i,
                ))
            db.commit()

    finally:
        db.close()
