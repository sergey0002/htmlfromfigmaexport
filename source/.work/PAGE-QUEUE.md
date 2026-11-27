# Очередь страниц

> Создано из manifest.json. Не редактируйте статусы здесь.

Инвентаризация: **unconfirmed**. Страниц: 15, подтверждено: 15.

| № | Страница | Эталон | Файл | Подтверждение | Работа | Проверки |
|---:|---|---|---|---|---|---|
| 1 | Главная | `/` | `index.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 2 | О партии | `/#about` | `about.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 3 | Программа | `/#program` | `program.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 4 | Люди | `/#people` | `people.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 5 | Деятельность | `/#activity` | `activity.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 6 | Регионы | `/#regions` | `regions.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 7 | Медиа | `/#media` | `media.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 8 | Приёмная | `/#reception` | `reception.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 9 | Контакты | `/#contacts` | `contacts.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 10 | Программа: Экономика | `/#program/economy` | `program/economy.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 11 | Программа: Образование | `/#program/education` | `program/education.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 12 | Программа: Здравоохранение | `/#program/health` | `program/health.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 13 | Программа: Культура и язык | `/#program/culture` | `program/culture.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 14 | Программа: Безопасность | `/#program/security` | `program/security.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |
| 15 | Программа: Внешняя политика | `/#program/world` | `program/world.html` | confirmed | pending | static: not_run, browser: not_run, manual: not_run |

## Неясные ссылки и ограничения

- `/#about/leadership`: Ссылка «Биография»; App передаёт AboutPage без detail, отдельная страница не подтверждена. — требуется решение
- `#`: Социальные ссылки и часть документов — заглушки; адреса не подтверждены. — требуется решение
- ``program/${item.id}``: src/App.tsx:378: не найден конечный набор параметров — требуется решение
- `/#about/leadership`: src/App.tsx:409: вложенный маршрут требует проверки обработчика и содержимого — требуется решение
- Статическая инвентаризация: живой эталон не запускался; полнота маршрутов и состояний не подтверждена.
- Внешние фотографии Unsplash и шрифты Google Fonts: доступность и права не подтверждены.
- Формы показывают локальный успех; действующий backend не подтверждён.
- AST обнаруживает только поддерживаемые конструкции; агент обязан проверить маршруты, состояния, алиасы и неподтверждённые ссылки.

## Состояния

- **Главная**: mobile-menu, join-modal, volunteer-modal, idea-modal, slider, region-map
- **О партии**: mobile-menu, join-modal, volunteer-modal, idea-modal
- **Программа**: mobile-menu, join-modal, volunteer-modal, idea-modal
- **Люди**: mobile-menu, join-modal, volunteer-modal, idea-modal
- **Деятельность**: mobile-menu, join-modal, activity-filter, volunteer-modal, idea-modal
- **Регионы**: mobile-menu, join-modal, region-map, volunteer-modal, idea-modal
- **Медиа**: mobile-menu, join-modal, media-tabs, volunteer-modal, idea-modal
- **Приёмная**: mobile-menu, join-modal, reception-form, faq, volunteer-modal, idea-modal
- **Контакты**: mobile-menu, join-modal, volunteer-modal, idea-modal
- **Программа: Экономика**: mobile-menu, join-modal, volunteer-modal, idea-modal
- **Программа: Образование**: mobile-menu, join-modal, volunteer-modal, idea-modal
- **Программа: Здравоохранение**: mobile-menu, join-modal, volunteer-modal, idea-modal
- **Программа: Культура и язык**: mobile-menu, join-modal, volunteer-modal, idea-modal
- **Программа: Безопасность**: mobile-menu, join-modal, volunteer-modal, idea-modal
- **Программа: Внешняя политика**: mobile-menu, join-modal, volunteer-modal, idea-modal
