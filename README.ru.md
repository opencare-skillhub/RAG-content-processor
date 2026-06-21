# FastGPT Content Processor

Инструмент командной строки для управления и обработки содержимого базы знаний FastGPT, включая запросы к базе знаний, поиск контента, загрузку файлов, а также загрузку, очистку и отправку статей из WeChat.

## Возможности

- **list-datasets**: список всех наборов данных FastGPT
- **list-collections**: список статей/коллекций в наборе данных
- **search**: семантический поиск по базе знаний
- **upload-file**: загрузка одного Markdown-файла
- **upload-folder**: пакетная загрузка Markdown-файлов из папки
- **download-wechat**: пакетная загрузка статей WeChat через MCP
- **clean-wechat**: двухэтапная очистка Markdown из WeChat
- **download-and-clean**: комплексный рабочий процесс: загрузка → очистка → отправка

## Установка и использование

### Рекомендуемый способ: uv

```bash
cd fastgpt-content-processor
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
```

### Альтернативный способ: venv

```bash
cd fastgpt-content-processor
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

### Запуск команд

```bash
python3 main.py --help
python3 main.py list-datasets
python3 main.py search --dataset-id 697b19a113081cf58b45cac3 --query "KRAS мутация"
```

## Примеры использования

### Список всех наборов данных

```bash
python3 main.py list-datasets
```

### Список статей в наборе данных

```bash
python3 main.py list-collections --dataset-id 697b19a113081cf58b45cac3
```

### Поиск по базе знаний

```bash
python3 main.py search --dataset-id 697b19a113081cf58b45cac3 --query "KRAS мутация"
```

### Загрузка одного файла

```bash
python3 main.py upload-file --file article.md --dataset-id 697b19a113081cf58b45cac3
```

### Пакетная загрузка папки

```bash
python3 main.py upload-folder --folder ./articles --dataset-id 697b19a113081cf58b45cac3
```

### Загрузка статей WeChat

Создайте файл `urls.txt` с одним URL-адресом статьи WeChat на строку:

```bash
python3 main.py download-wechat --urls urls.txt --output ./wechat-downloads
```

### Очистка статей WeChat

```bash
python3 main.py clean-wechat --input ./wechat-downloads --output ./cleaned-articles
```

### Комплексный процесс (загрузка → очистка → отправка)

```bash
python3 main.py download-and-clean \
  --urls urls.txt \
  --output ./wechat-downloads \
  --cleaned-output ./cleaned-articles \
  --dataset-id 697b19a113081cf58b45cac3
```

## Структура проекта

```
fastgpt-content-processor/
├── main.py                      # Точка входа CLI
├── fastgpt_sync.py              # Обёртка API FastGPT
├── fetchers/                    # Модули загрузки контента
├── cleaners/                    # Модули очистки контента
├── utils/                       # Утилиты
├── tests/                       # Тесты
├── .env.example                 # Шаблон переменных окружения
├── requirements.txt             # Зависимости Python
└── README.md                    # Документация
```

## Тестирование

См. [`tests/README.md`](tests/README.md) для описания области тестирования и предложенных тем.

```bash
python3 -m pytest
```

## Дорожная карта

### Краткосрочная: воспроизводимость и верификация
- Единообразное использование `python3` и документация виртуального окружения
- Добавление тестов основной логики
- Чёткие границы для FastGPT, MCP и примеров скриптов

### Среднесрочная: поддерживаемость и сотрудничество
- Унификация конвейера очистки
- Оптимизация параметров CLI
- Режим dry-run / предпросмотр
- Детальное логирование и статистика

### Долгосрочная: расширяемость и платформенность
- Плагинная архитектура загрузчиков / очистителей / адаптеров
- Поддержка дополнительных источников контента
- Рабочие процессы на основе конвейеров
- Настраиваемые правила и оркестрация пакетных заданий

## Как внести вклад

Приветствуются вклады в код, документацию, тесты и опыт использования.

### Рекомендуемые практики
- Сначала откройте issue для описания требования или проблемы
- Добавьте тесты перед изменением логики
- Поддерживайте актуальность документации
- Предоставляйте примеры ввода/вывода при добавлении новых правил очистки

## Благодарности

Благодарим следующие проекты за вдохновение и материалы:

- [wechat-article-downloader](https://github.com/qiye45/wechatDownload)
- [baoyu-format-markdown](https://github.com/baoyu-tech/markdown-formatter)
- [markdown-frontmatter-doctor](https://github.com/example/frontmatter-doctor)
- [Документация FastGPT API](https://doc.fastgpt.in/docs/development/api/)

## Лицензия

MIT License

---

**Другие языки**: [中文](README.md) | [English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md)
