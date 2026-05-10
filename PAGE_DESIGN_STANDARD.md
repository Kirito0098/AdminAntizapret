# Эталонный стандарт дизайна страниц — AdminAntizapret

> Документ описывает точную архитектуру, компоненты и правила стиля страницы `index`.
> При переработке других страниц строго следовать этому стандарту.

---

## 1. Глобальная оболочка (base.html)

### HTML-скелет
```html
<body class="index-page-dark [settings-nav-merged]">
  <div class="app-shell">
    <nav class="navigation"> … </nav>
    <main class="app-main">
      {% block content %}{% endblock %}
    </main>
  </div>
</body>
```

### Класс `body`
| Условие | Класс |
|---------|-------|
| Страницы: `index`, `edit_files`, `server_monitor`, `logs_dashboard`, `settings` | `index-page-dark` |
| Страница `settings` дополнительно | `settings-nav-merged` |

> **Правило:** Все основные страницы используют `index-page-dark`. Это переключает фон на тёмный градиент `#10161a → #0e1418`.

---

## 2. Навигационная панель (`.navigation`)

### Структура
```html
<nav class="navigation">
  <!-- Бренд-блок -->
  <div class="nav-brand-row">
    <div class="nav-brand">
      <span class="nav-brand-kicker">AdminAntizapret</span>
      <strong class="nav-brand-title">Control Panel</strong>
    </div>
    <button class="nav-mobile-toggle">☰</button>
  </div>

  <!-- Контент навигации -->
  <div class="nav-content" id="navMobileContent">
    <div class="nav-group">
      <a class="nav-link [is-active]">Главная</a>

      <!-- Группа с подменю -->
      <div class="nav-settings-group [is-open]">
        <a class="nav-link nav-link-settings">
          <span>Название</span>
          <span class="nav-settings-caret">▾</span>
        </a>
        <div class="nav-settings-submenu">
          <a class="nav-sublink [is-active]">Подраздел</a>
        </div>
      </div>
    </div>

    <!-- Блок пользователя — всегда внизу -->
    <div class="user-info-block">
      <div class="user-info">
        <span class="username">{{ username }}</span>
        <span class="user-role role-admin|role-viewer">Admin|Viewer</span>
      </div>
      <a class="nav-link nav-link-logout">Выход</a>
    </div>
  </div>
</nav>
```

### Параметры навигации
| Свойство | Значение |
|----------|----------|
| Ширина | `264px` (flex: 0 0 264px) |
| Позиция | `sticky`, `top: 1rem` |
| Граница | `border-radius: 14px` |
| `max-height` | `calc(100vh - 2rem)` |
| Z-index | `80` |

### Классы-модификаторы
- `.nav-link.is-active` — активная ссылка (зелёный градиент)
- `.nav-sublink.is-active` — активная подссылка (синий градиент)
- `.nav-settings-group.is-open` — раскрытое подменю (кaret поворачивается)
- `.nav-link-logout` — кнопка выхода (красноватый фон)

---

## 3. Основная область (`.app-main`)

```css
.app-main {
  flex: 1;
  min-width: 0;
  padding: 1rem 1.2rem 1.4rem;
}
```

Всё содержимое страницы размещается внутри `.app-main` через `{% block content %}`.

---

## 4. Обёртка страницы — Unified Wrapper

### Базовая обёртка (для большинства страниц)
```html
<div class="page-unified-wrapper page-unified-grid">
  <!-- Содержимое страницы -->
</div>
```

| Класс | Поведение |
|-------|-----------|
| `page-unified-wrapper` | `width: min(1320px, 96%)`, `margin: 2rem auto` |
| `page-unified-grid` | `gap: 1rem` |

### Специальная обёртка для индекс-страницы
```html
<div class="index-container page-unified-wrapper page-unified-grid sidebar-ops-layout">
```

Добавляет `sidebar-ops-layout`, который:
- Определяет CSS-переменные цветов (`--ops-*`)
- На ≥ 1024px растягивает до `min(1580px, 100%)`
- Выравнивает содержимое по `flex-direction: column, gap: 1.2rem`

---

## 5. Карточка — `page-unified-card`

Основной контейнер-карточка для любого блока на странице.

```css
.page-unified-card {
  background: rgba(8, 14, 17, 0.78);       /* --theme-logs-surface */
  border: 1px solid rgba(84, 168, 133, 0.24); /* --theme-primary-alpha-24 */
  border-radius: 14px;
  padding: 1rem;
}
```

**Вариант плотный:** `.page-unified-card--tight` → `padding: 0.75rem 0.9rem`

> **Правило:** Каждый смысловой блок на странице — карточка. Не использовать `<div>` без `page-unified-card` для секций с контентом.

---

## 6. Вкладки — `page-unified-tabs` / `page-unified-tab-btn`

```html
<div class="protocol-tabs page-unified-tabs">
  <button class="tab-btn page-unified-tab-btn active" data-protocol="openvpn">
    <span class="protocol-icon">🔒</span>
    <span>OpenVPN</span>
  </button>
  <!-- ... -->
</div>
```

| Состояние | Класс |
|-----------|-------|
| Обычная вкладка | `page-unified-tab-btn` |
| Активная | `page-unified-tab-btn active` или `page-unified-tab-btn is-active` |

Стили:
- `border-radius: 9px`, `padding: 0.45rem 0.85rem`
- Активная: зелёный градиент, яркая граница

---

## 7. Тулбар поиска — `page-unified-toolbar`

```html
<div class="search-and-filter page-unified-toolbar">
  <div class="search-box"> … </div>
  <div class="filter-buttons">
    <button class="filter-btn [active]" data-filter="all">Все</button>
    …
  </div>
</div>
```

На мобильных (≤ 1024px): поиск встаёт выше фильтров (`flex-wrap: wrap`).

---

## 8. Структура index-страницы (эталон)

```
sidebar-ops-layout
├── index-ops-header-card (page-unified-card)   ← KPI-шапка
│   ├── index-ops-header-main
│   │   └── h1.index-ops-subtitle               ← Подзаголовок-описание
│   └── index-ops-kpi-strip                     ← 4 KPI-карточки
│       ├── article.index-kpi-card × 4
│       │   ├── span.index-kpi-label
│       │   └── strong.index-kpi-value [--warn|--danger]
└── index-ops-grid
    ├── main-content (page-unified-card)         ← Основная таблица + вкладки
    │   ├── search-and-filter (page-unified-toolbar)
    │   ├── protocol-tabs (page-unified-tabs)
    │   └── tab-content
    │       └── tab-pane [active] × 3 протоколов
    │           └── table.config-table.client-grid-table
    └── index-ops-rail (page-unified-card)       ← Правая боковая панель (320px)
        ├── index-rail-section--traffic          ← Live-трафик
        ├── index-rail-section (Алерты)
        └── index-rail-section--services        ← Статус служб
```

### Grid ops-grid
```css
.sidebar-ops-layout .index-ops-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 1rem;
  align-items: start;
}
```

На ≤ 1024px `index-ops-rail` уходит в отдельную строку.

---

## 9. KPI-шапка

```html
<section class="index-ops-header-card page-unified-card">
  <div class="index-ops-header-main">
    <h1 class="index-ops-subtitle">Описание рабочего пространства.</h1>
  </div>
  <div class="index-ops-kpi-strip">
    <article class="index-kpi-card">
      <span class="index-kpi-label">МЕТРИКА</span>
      <strong class="index-kpi-value">42</strong>
    </article>
    <!-- × 4, можно --warn или --danger для значения -->
  </div>
</section>
```

KPI-strip: `grid-template-columns: repeat(4, minmax(0, 1fr))`.

---

## 10. Правая рейлс-панель (`.index-ops-rail`)

```html
<aside class="index-ops-rail page-unified-card">

  <!-- Секция трафика -->
  <section class="index-rail-section index-rail-section--traffic" data-state="loading|ok|error">
    <h3 class="index-rail-title">Трафик (live)</h3>
    <p class="index-traffic-mini-note">…</p>
    <div class="index-traffic-mini-grid">
      <article class="index-traffic-mini-card"> … </article>
    </div>
    <ul class="index-traffic-mini-list">
      <li><span>Период</span><strong id="...">-</strong></li>
    </ul>
  </section>

  <!-- Секция алертов -->
  <section class="index-rail-section">
    <h3 class="index-rail-title">Алерты</h3>
    <div class="index-alert-stack">
      <article class="index-alert-card index-alert-card--danger|--warn|--neutral|--ok">
        <h4>Заголовок</h4>
        <p>Описание.</p>
      </article>
    </div>
  </section>

  <!-- Секция статуса служб -->
  <section class="index-rail-section index-rail-section--services">
    <h3 class="index-rail-title">Статус служб</h3>
    <ul class="index-service-status-list">
      <li class="index-service-project-item">
        <div class="index-service-project-name">Группа</div>
        <ul class="index-service-project-services">
          <li class="index-service-status-item">
            <div class="index-service-meta">
              <span class="index-service-name">Служба</span>
              <span class="index-service-desc">Описание</span>
            </div>
            <span class="index-service-state index-service-state--ok|--warn|--error|--unknown">
              Запущена
            </span>
          </li>
        </ul>
      </li>
    </ul>
  </section>

</aside>
```

---

## 11. Строки таблицы клиентов

### HTML строки (tr)
```html
<tr class="client-row"
  data-client-name="{{ name }}"
  data-protocol="openvpn|amneziawg|wg"
  data-cert-state="active|expiring|expired"
  data-cert-days="{{ days }}"
  data-blocked="0|1"
  data-can-block="0|1"
  data-can-manage="0|1"
  data-delete-option="2|5"
  data-download-vpn-url="…"
  data-download-az-url="…"
  data-one-time-vpn-endpoint="…"
  data-one-time-az-endpoint="…"
  data-qr-vpn-url="…"      <!-- только WG/AWG -->
  data-qr-az-url="…">      <!-- только WG/AWG -->
  <td class="client-name client-name-cell">
    <div class="client-name-main">{{ name }}</div>
    <span class="client-block-badge is-active|is-blocked">Активный|Заблокирован</span>
    <!-- Только для admin: cert-meta -->
    <div class="client-cert-meta active|expiring|expired">
      <div>До: 2025-01-01</div>
      <div>Осталось: 90 дн.</div>
    </div>
    <div class="client-card-meta">
      <span class="client-card-chip is-protocol">OpenVPN</span>
      <span class="client-card-chip is-vpn">VPN</span>
      <span class="client-card-chip is-az">AZ</span>
    </div>
    <div class="client-card-hint">Открыть действия и график</div>
  </td>
</tr>
```

### Статусные чипы `.client-block-badge`
| Класс | Цвет |
|-------|------|
| `.is-active` | Зелёный (`--theme-primary`) |
| `.is-blocked` | Красный (`--theme-danger`) |

### Чипы протокола `.client-card-chip`
| Класс | Значение |
|-------|----------|
| `.is-protocol` | Синий — имя протокола |
| `.is-vpn` | Зелёный — VPN-конфиг |
| `.is-az` | Пурпурный — AZ-конфиг |

---

## 12. Модальные окна

### Паттерн модального окна
```html
<!-- Открытие: убрать атрибут hidden, добавить класс is-open -->
<div class="[prefix]-modal" id="…" hidden>
  <div class="[prefix]-backdrop" data-[prefix]-close></div>
  <div class="[prefix]-dialog" role="dialog" aria-modal="true">
    <button class="[prefix]-close" data-[prefix]-close>×</button>
    <div class="[prefix]-header">
      <h3 id="…">Заголовок</h3>
      <p>Описание.</p>
    </div>
    <!-- Контент -->
    <div class="[prefix]-actions">
      <button class="download-button" data-[prefix]-close>Отмена</button>
      <button class="btn-primary">Действие</button>
    </div>
  </div>
</div>
```

| Модал | Префикс | Ширина dialog |
|-------|---------|---------------|
| Добавить клиента | `add-client` | `min(620px, 95vw)` |
| Детали клиента | `client-details` | `min(1080px, 95vw)` |
| QR-код | `qr-modal-container` | `max-width: 30%` (90% на мобильном) |

Все модалы используют `backdrop-filter: blur(6px)` в `index-page-dark`.

---

## 13. Модал детали клиента

```html
<div class="client-details-modal" id="clientDetailsModalMain" hidden>
  <div class="client-details-backdrop" data-client-details-close></div>
  <div class="client-details-dialog">
    <button class="client-details-close">×</button>
    <div class="client-details-header">
      <h3>Имя клиента</h3>
      <p class="client-details-summary">Загрузка…</p>
    </div>

    <!-- Секция действий -->
    <section class="client-details-section client-details-actions-section">
      <div class="client-details-section-title">Действия</div>
      <div class="client-details-actions"> … </div>
    </section>

    <!-- Секция трафика -->
    <section class="client-details-section">
      <div class="client-details-section-title">Трафик клиента (БД)</div>
      <div class="client-details-quick">…</div>
      <div class="client-details-range">
        <button class="client-details-range-btn" data-range="1h">1 час</button>
        <button class="client-details-range-btn" data-range="24h">24 часа</button>
        <button class="client-details-range-btn" data-range="7d">7 дней</button>
        <button class="client-details-range-btn" data-range="30d">30 дней</button>
        <button class="client-details-range-btn" data-range="all">За все время</button>
      </div>
      <div class="client-details-meta">…</div>
      <div class="client-details-chart-wrap">
        <canvas id="clientDetailsTrafficChartMain"></canvas>
      </div>
    </section>

    <!-- Секция подключений -->
    <section class="client-details-section">
      <div class="client-details-section-title">Подключения (IP, устройство, версия)</div>
      <div class="client-details-connections">…</div>
    </section>
  </div>
</div>
```

---

## 14. Цветовая палитра (token-система)

Все цвета берутся **только** из `theme.css` через CSS-переменные. Никаких хардкодов.

### Семантические токены
| Токен | Назначение |
|-------|-----------|
| `--theme-primary` | `#3fa083` — акцент, кнопки ОК, бейджи активных |
| `--theme-danger` | `#d5675f` — ошибки, заблокированные, истёкшие |
| `--theme-warning` | `#e3a65b` — предупреждения, скоро истекают |
| `--theme-secondary` | `#5a9dcb` — вторичный акцент |
| `--theme-text-main` | `#eaf1f4` — основной текст |
| `--theme-text-muted` | `#8ea2ad` — приглушённый текст, лейблы |
| `--theme-logs-surface` | `rgba(8,14,17,0.78)` — фон карточек |
| `--theme-primary-alpha-24` | `rgba(63,160,131,0.24)` — граница карточек |

### Локальные переменные `sidebar-ops-layout`
```css
--ops-accent:       #3fa083
--ops-accent-soft:  #58b2a3
--ops-warn:         #e7a63b
--ops-danger:       #d5675f
--ops-text:         #eaf1f4
--ops-muted:        #9caeb8
--ops-border:       #314049
--ops-surface:      #1c2328
--ops-surface-soft: #222b31
--ops-bg:           #151a1d
```

---

## 15. Типографика

| Элемент | Класс/тег | font-size | font-weight |
|---------|-----------|-----------|-------------|
| Главный заголовок | `.index-ops-title` | `clamp(1.65rem, 2.6vw, 2.15rem)` | 700 |
| Подзаголовок-описание | `.index-ops-subtitle` | `0.92rem` | 400 |
| Заголовок секции | `.index-rail-title` | ~`0.85rem` | 700 |
| KPI-лейбл | `.index-kpi-label` | `0.71rem`, uppercase | 400 |
| KPI-значение | `.index-kpi-value` | `1.54rem` | 700 |
| Вкладка | `.page-unified-tab-btn` | `0.86rem` | 600 |
| Nav-ссылка | `.nav-link` | `0.89rem` | 600 |
| Nav-подссылка | `.nav-sublink` | `0.79rem` | 600 |
| Шрифт | Poppins | — | 400, 500, 600, 700 |

---

## 16. Брейкпойнты (responsive)

| Ширина | Поведение |
|--------|-----------|
| `≥ 1024px` | Навигация всегда видна, `index-ops-grid` — 2 колонки |
| `< 1024px` | Навигация скрыта, кнопка-гамбургер; grid в 1 колонку |
| `≤ 760px` | `page-unified-wrapper` → `width: 98%` |
| `≤ 430px` | `page-unified-wrapper` → `width: 100%`, без горизонтального отступа; `page-unified-tabs` → 2-col grid |

---

## 17. Уведомления (toast)

Создаются динамически через JS. Не верстать вручную.

```html
<!-- Создаётся JS-кодом в base.html -->
<div class="notification notification-success|notification-info|notification-error">
  Текст сообщения
</div>
```

Анимация `fadeInOut 3s`, позиция `fixed top:20px right:20px`.

---

## 18. Кнопки

| Вариант | Класс | Применение |
|---------|-------|-----------|
| Основная | `.btn-primary` | Подтверждение действия в модале |
| Вторичная / отмена | `.download-button` | Скачивание, отмена в модале |
| Фильтр | `.filter-btn [.active]` | Панель фильтрации |
| Вкладка-кнопка | `.page-unified-tab-btn [.active]` | Переключение протоколов |
| Добавить (модал) | `.add-client-launch-btn.page-unified-tab-btn` | Кнопка в строке вкладок |

---

## 19. Скрипты (блок scripts)

```html
{% block scripts %}
<!-- Chart.js подключается только на страницах с графиками -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@latest/dist/chart.umd.min.js"></script>
<script src="{{ url_for('static', filename='assets/js/page_specific.js') }}"></script>
{% endblock %}
```

---

## 20. Чеклист при создании новой страницы

- [ ] `body` имеет класс `index-page-dark`
- [ ] Контент обёрнут в `page-unified-wrapper [page-unified-grid]`
- [ ] Каждый смысловой блок — `page-unified-card`
- [ ] Вкладки через `page-unified-tabs` / `page-unified-tab-btn`
- [ ] Тулбар/поиск — `page-unified-toolbar`
- [ ] Цвета только через CSS-переменные `--theme-*`
- [ ] Шрифт Poppins (подключён глобально через `styles_index.css`)
- [ ] Модалы следуют паттерну с backdrop + dialog + close-кнопкой
- [ ] CSRF-токен в каждой форме: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`
- [ ] Все интерактивные кнопки имеют `type="button"` (кроме submit)
- [ ] Навигация — не трогать, она в `base.html`
- [ ] Flash-уведомления обрабатываются автоматически через `base.html`
