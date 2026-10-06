import tgscraper as tg
from datetime import datetime, timezone
from typing import List, Dict, Optional, Union


class TgParser:


    @staticmethod
    def _format_date(dt: Union[datetime, str, None]) -> Optional[str]:
        """
        Приводит дату к формату ISO (YYYY-MM-DD), который ожидает tgscraper.
        Принимает datetime, строку или None.
        """
        if dt is None:
            return None
        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%d")
        # Если передана строка — возвращаем как есть (tgscraper сам разберёт)
        return str(dt)

    def get_channel_messages(
        self,
        channel: Union[str, int],
        date_from: Union[datetime, str],
        date_to: Union[datetime, str],
        max_messages: Optional[int] = None,
    ) -> List:
        """
        Получить сообщения из одного публичного канала за промежуток [date_from, date_to].

        :param channel: username (@name), ссылка (t.me/name) или просто name
        :param date_from: начало промежутка (datetime или строка YYYY-MM-DD)
        :param date_to: конец промежутка (datetime или строка YYYY-MM-DD)
        :param max_messages: ограничение на общее число сообщений (None — без лимита)
        :return: список объектов Message из tgscraper
        """
        since = self._format_date(date_from)
        until = self._format_date(date_to)

        posts = tg.scrape(
            str(channel),
            limit=max_messages,          # None = вся история в диапазоне
            since=since,
            until=until,
        )
        return posts

    from datetime import datetime, timezone
    from typing import List, Dict, Optional, Union




    @staticmethod
    def _parse_dt(value: Union[datetime, str, None]) -> Optional[datetime]:
        """
        Приводит дату к aware-UTC datetime.
        Принимает datetime (naive или aware) или строку.
        """
        if value is None:
            return None

        if isinstance(value, datetime):
            dt = value
        else:
            # Строка: пробуем ISO, иначе просто YYYY-MM-DD
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                dt = datetime.strptime(str(value), "%Y-%m-%d")

        # Если datetime наивный — считаем его UTC
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def get_multiple_channels(
            self,
            channels: List[Union[str, int]],
            date_from: Union[datetime, str],
            date_to: Union[datetime, str],
            max_messages_per_channel: Optional[int] = None,
    ) -> Dict[str, List]:
        """
        Получить сообщения из нескольких каналов за промежуток.
        Каналы обрабатываются конкурентно через tg.scrape_many().
        """
        since = self._format_date(date_from)
        until = self._format_date(date_to)

        # Границы как aware-UTC datetime для корректного сравнения
        since_dt = self._parse_dt(date_from)
        # Конец дня для date_to
        until_dt = self._parse_dt(date_to)
        if until_dt is not None:
            until_dt = until_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

        raw_results = tg.scrape_many(
            [str(ch) for ch in channels],
            limit=max_messages_per_channel,
        )

        results: Dict[str, List] = {}
        for ch, data in raw_results.items():
            if isinstance(data, Exception):
                print(f"   Ошибка при обработке {ch}: {data}")
                results[str(ch)] = []
                continue

            filtered = []
            for msg in data:
                msg_dt = self._parse_dt(getattr(msg, "date", None))
                if msg_dt is None:
                    continue

                if since_dt and msg_dt < since_dt:
                    continue
                if until_dt and msg_dt > until_dt:
                    continue

                filtered.append(msg)

            results[str(ch)] = filtered
            print(f"   Получено сообщений: {len(filtered)}")

        return results

    @staticmethod
    def messages_to_dicts(messages: List) -> List[Dict]:
        """
        Преобразует список Message (tgscraper) в список обычных словарей.

        Доступные поля Message (согласно документации tgscraper):
        id, channel, url, date, text, html, views, author, edited,
        forwarded_from, reply_to, media, reactions, hashtags, mentions, links.
        """
        result = []
        for m in messages:
            result.append({
                "id": getattr(m, "id", None),
                "channel": getattr(m, "channel", None),
                "url": getattr(m, "url", None),
                "date": getattr(m, "date", None),
                "text": getattr(m, "text", "") or "",
                "html": getattr(m, "html", None),
                "views": getattr(m, "views", None),
                "author": getattr(m, "author", None),
                "edited": getattr(m, "edited", None),
                "forwarded_from": getattr(m, "forwarded_from", None),
                "reply_to": getattr(m, "reply_to", None),
                "media": getattr(m, "media", None),
                "media_types": getattr(m, "media_types", None),
                "reactions": getattr(m, "reactions", None),
                "hashtags": getattr(m, "hashtags", None),
                "mentions": getattr(m, "mentions", None),
                "links": getattr(m, "links", None),
            })
        return result


if __name__ == "__main__":
    channels = [
        "durov",
        "@telegram",
    ]

    date_from = "2024-01-01"
    date_to = "2024-06-01"

    parser = TgParser()

    print("=== Один канал ===")
    messages = parser.get_channel_messages(
        "durov",
        date_from=date_from,
        date_to=date_to,
        max_messages=500,
    )
    for d in TgParser.messages_to_dicts(messages[:3]):
        print(f"[{d['date']}] {d['text'][:100]!r}")

    print("\n=== Несколько каналов ===")
    data = parser.get_multiple_channels(
        channels,
        date_from=date_from,
        date_to=date_to,
        max_messages_per_channel=500,
    )
    for channel, msgs in data.items():
        print(f"\n--- {channel} ({len(msgs)} сообщений) ---")
        for d in TgParser.messages_to_dicts(msgs[:3]):
            print(f"[{d['date']}] {d['text'][:100]!r}")