-- Простые запросы к backend/data/vacancies.duckdb.
-- Подключитесь к этому файлу базы в PyCharm или другом SQL-клиенте.
-- Запускайте запросы по одному. Все запросы только читают данные.

-- 1. Какие поля есть в таблице.
DESCRIBE vacancies;

-- 2. Сколько всего сохранено вакансий.
SELECT COUNT(*) AS total_vacancies
FROM vacancies;

-- 3. Последние 20 сохранённых или обновлённых вакансий.
SELECT title, company, channel_name, message_id, published_date, saved_at
FROM vacancies
ORDER BY saved_at DESC
LIMIT 20;

-- 4. Поиск слова Python в названии или исходном тексте.
-- Замените Python на нужное слово.
SELECT title, company, channel_name, published_date
FROM vacancies
WHERE title ILIKE '%Python%'
   OR json_extract_string(payload, '$.raw_text') ILIKE '%Python%'
ORDER BY published_date DESC NULLS LAST;

-- 5. Количество вакансий по каналам.
SELECT channel_name, COUNT(*) AS vacancy_count
FROM vacancies
GROUP BY channel_name
ORDER BY vacancy_count DESC;

-- 6. Вакансии, опубликованные за последние 7 дней.
SELECT title, company, channel_name, published_date
FROM vacancies
WHERE published_date BETWEEN CURRENT_DATE - INTERVAL '7 days' AND CURRENT_DATE
ORDER BY published_date DESC;

-- 7. Поля из JSON: зарплата, формат работы и ссылка на сообщение.
SELECT
    title,
    company,
    json_extract_string(payload, '$.salary.min_amount') AS salary_from,
    json_extract_string(payload, '$.salary.max_amount') AS salary_to,
    json_extract_string(payload, '$.salary.currency') AS currency,
    json_extract_string(payload, '$.salary.period') AS salary_period,
    json_extract_string(payload, '$.work_format') AS work_format,
    json_extract_string(payload, '$.source.original_url') AS url
FROM vacancies
ORDER BY published_date DESC NULLS LAST
LIMIT 20;

-- 8. Исходные тексты последних 5 вакансий.
SELECT title, channel_name, json_extract_string(payload, '$.raw_text') AS raw_text
FROM vacancies
ORDER BY saved_at DESC
LIMIT 5;
