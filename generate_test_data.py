import base64
import hashlib
import random
from datetime import date, datetime, timedelta, timezone
from getpass import getuser
from uuid import uuid4

import psycopg


DB = {
    "dbname": "acid_sound",
    "user": getuser(),
    "password": "",
    "host": "localhost",
    "port": 5432,
}

USER_COUNT = 100
ARTIST_COUNT = 20
ALBUM_COUNT = 40
SONG_COUNT = 300
LISTENINGS_PER_PREMIUM = 30

ACTION_TABLES = {
    1: ("map_actions", "map_id"),
    2: ("playlist_actions", "playlist_id"),
    3: ("artist_actions", "artist_id"),
    4: ("genre_actions", "genre_id"),
    5: ("album_actions", "album_id"),
    6: ("song_actions", "song_id"),
    7: ("rating_actions", "rating_id"),
    8: ("comment_actions", "comment_id"),
    9: ("listening_actions", "listening_id"),
}


def insert_id(cur, query, values):
    cur.execute(query, values)
    return cur.fetchone()[0]


def add_action(cur, user_id, category, action_type, time, object_id):
    action_id = insert_id(cur, """
        INSERT INTO public.user_actions (user_id, category, action_type, performed_at)
        VALUES (%s, %s, %s, %s) RETURNING action_id
    """, (user_id, category, action_type, time))
    table, column = ACTION_TABLES[category]
    cur.execute(f"INSERT INTO public.{table} (action_id, {column}) VALUES (%s, %s)",
                (action_id, object_id))


def main():
    random.seed(42)
    run = uuid4().hex[:10]
    start = datetime.now(timezone.utc) - timedelta(days=90)
    names = [("Анна", "Соколова"), ("Михаил", "Орлов"), ("Елена", "Волкова"),
             ("Иван", "Белов"), ("Ольга", "Морозова"), ("Дмитрий", "Крылов")]
    moods = ["Спокойное", "Радостное", "Рабочее", "Энергичное"]
    contexts = ["Дом", "Работа", "Прогулка", "Транспорт"]
    texts = ["Хорошая мелодия.", "Нравится звучание.", "Интересная аранжировка."]
    titles = ["Ночной ветер", "Новый день", "Тихий берег", "Дорога домой", "Первый снег"]
    digest = hashlib.pbkdf2_hmac("sha256", b"test12345", run.encode(), 600000)
    password_hash = f"pbkdf2_sha256$600000${run}${base64.b64encode(digest).decode()}"

    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:
            # Пользователи.
            users = []
            for i in range(USER_COUNT):
                first, last = random.choice(names)
                premium = i % 3 == 0
                birthday = date(start.year - random.randint(18, 45), random.randint(1, 12),
                                random.randint(1, 28))
                user_id = insert_id(cur, """
                    INSERT INTO public.users
                        (full_name, birth_date, login, password_hash, phone_number, is_premium)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING user_id
                """, (f"{first} {last}", birthday, f"test_{run}_{i + 1}", password_hash,
                      f"+7900{i:07d}", premium))
                users.append((user_id, premium))
            premium_users = [user_id for user_id, premium in users if premium]
            actor = premium_users[0]
            print("Пользователи добавлены.", flush=True)

            # Жанры, исполнители и альбомы.
            for name in ["Рок", "Поп", "Электроника", "Джаз", "Инди", "Эмбиент"]:
                cur.execute("""
                    INSERT INTO public.genres (name) VALUES (%s)
                    ON CONFLICT (name) DO NOTHING RETURNING genre_id
                """, (name,))
                row = cur.fetchone()
                if row:
                    add_action(cur, actor, 4, "create", start, row[0])
            cur.execute("SELECT genre_id FROM public.genres ORDER BY genre_id")
            genres = [row[0] for row in cur.fetchall()]
            artists = []
            for i in range(ARTIST_COUNT):
                artist_id = insert_id(cur, """
                    INSERT INTO public.artists (nickname, description)
                    VALUES (%s, %s) RETURNING artist_id
                """, (f"Проект {run}-{i + 1}", "Тестовый музыкальный исполнитель"))
                artists.append(artist_id)
                add_action(cur, actor, 3, "create", start, artist_id)
            albums = []
            for i in range(ALBUM_COUNT):
                artist_id = random.choice(artists)
                album_id = insert_id(cur, """
                    INSERT INTO public.albums (artist_id, genre_id, title, release_year)
                    VALUES (%s, %s, %s, %s) RETURNING album_id
                """, (artist_id, random.choice(genres), f"Альбом {run}-{i + 1}",
                      random.randint(start.year - 5, start.year)))
                albums.append((album_id, artist_id))
                add_action(cur, actor, 5, "create", start + timedelta(days=1), album_id)

            # Песни: часть без альбома, часть загружена премиум-пользователями.
            songs = []
            for i in range(SONG_COUNT):
                album_id, artist_id = random.choice(albums)
                if random.random() < 0.2:
                    album_id = None
                    artist_id = random.choice(artists)
                uploaded_by = random.choice(premium_users) if random.random() < 0.3 else None
                created_at = start + timedelta(days=2, minutes=i)
                duration = random.randint(90, 360)
                song_id = insert_id(cur, """
                    INSERT INTO public.songs
                        (artist_id, album_id, uploaded_by_user_id, uploaded_at,
                         title, lyrics, duration_seconds)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING song_id
                """, (artist_id, album_id, uploaded_by, created_at if uploaded_by else None,
                      f"{random.choice(titles)} {i + 1}", None, duration))
                song_genres = random.sample(genres, random.randint(1, min(3, len(genres))))
                for genre_id in song_genres:
                    cur.execute("INSERT INTO public.song_genres (song_id, genre_id) VALUES (%s, %s)",
                                (song_id, genre_id))
                songs.append({"id": song_id, "artist": artist_id,
                              "duration": duration, "genres": song_genres})
                add_action(cur, uploaded_by or actor, 6, "upload" if uploaded_by else "create",
                           created_at, song_id)
            print("Музыкальный каталог добавлен.", flush=True)
            active_artists = sorted({song["artist"] for song in songs})
            listening_count = 0

            for number, (user_id, premium) in enumerate(users, 1):
                day = start + timedelta(days=random.randint(20, 30))

                # Плейлисты и подписки.
                playlists = []
                for i in range(2):
                    created_at = day + timedelta(hours=i)
                    playlist_id = insert_id(cur, """
                        INSERT INTO public.playlists (user_id, title, created_at)
                        VALUES (%s, %s, %s) RETURNING playlist_id
                    """, (user_id, f"Моя подборка {i + 1}", created_at))
                    selection = random.sample(songs, min(10, len(songs)))
                    for song in selection:
                        cur.execute("INSERT INTO public.playlist_songs VALUES (%s, %s)",
                                    (playlist_id, song["id"]))
                    playlists.append((playlist_id, selection))
                    add_action(cur, user_id, 2, "create", created_at, playlist_id)
                subscriptions = random.sample(active_artists, min(3, len(active_artists)))
                for artist_id in subscriptions:
                    cur.execute("""
                        INSERT INTO public.artist_subscriptions (user_id, artist_id, subscribed_at)
                        VALUES (%s, %s, %s)
                    """, (user_id, artist_id, day + timedelta(hours=2)))
                    add_action(cur, user_id, 3, "subscribe", day + timedelta(hours=2), artist_id)

                # Оценки, реакции и комментарии.
                rated = random.sample(songs, min(15, len(songs)))
                scores = {}
                for song in rated:
                    score = random.randint(1, 10)
                    scores[song["id"]] = score
                    time = day + timedelta(days=2, minutes=random.randint(0, 1000))
                    rating_id = insert_id(cur, """
                        INSERT INTO public.ratings (user_id, song_id, score, rated_at)
                        VALUES (%s, %s, %s, %s) RETURNING rating_id
                    """, (user_id, song["id"], score, time))
                    add_action(cur, user_id, 7, "rate", time, rating_id)
                for song in rated[:10]:
                    reaction = 1 if scores[song["id"]] >= 6 else -1
                    cur.execute("INSERT INTO public.song_reactions VALUES (%s, %s, %s)",
                                (user_id, song["id"], reaction))
                    add_action(cur, user_id, 6, "like" if reaction == 1 else "dislike",
                               day + timedelta(days=3), song["id"])
                for song in rated[:3]:
                    time = day + timedelta(days=3, minutes=random.randint(1, 1000))
                    comment_id = insert_id(cur, """
                        INSERT INTO public.comments (user_id, song_id, body, published_at)
                        VALUES (%s, %s, %s, %s) RETURNING comment_id
                    """, (user_id, song["id"], random.choice(texts), time))
                    add_action(cur, user_id, 8, "comment", time, comment_id)

                # Подробные прослушивания только у премиум-пользователей.
                last_times = {}
                if premium:
                    for i in range(LISTENINGS_PER_PREMIUM):
                        source = ["search", "recommendation", "playlist", "subscription"][i % 4]
                        playlist_id = None
                        if source == "playlist":
                            playlist_id, selection = random.choice(playlists)
                            song = random.choice(selection)
                        elif source == "subscription":
                            song = random.choice([s for s in songs if s["artist"] in subscriptions])
                        else:
                            song = random.choice(songs)
                        time = day + timedelta(days=4 + random.randint(0, 30),
                                               minutes=random.randint(0, 1000))
                        listening_id = insert_id(cur, """
                            INSERT INTO public.listenings
                                (user_id, song_id, playlist_id, started_at,
                                 actual_duration_seconds, launch_source, playback_context)
                            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING listening_id
                        """, (user_id, song["id"], playlist_id, time,
                              random.randint(0, song["duration"]), source, random.choice(contexts)))
                        add_action(cur, user_id, 9, "listen", time, listening_id)
                        last_times[song["id"]] = max(time, last_times.get(song["id"], time))
                        listening_count += 1

                # Одна карта у обычного пользователя, три снимка у премиум-пользователя.
                top_songs = sorted(rated, key=lambda song: scores[song["id"]], reverse=True)[:5]
                top_artists = list(dict.fromkeys(song["artist"] for song in top_songs))
                top_genres = list(dict.fromkeys(g for song in top_songs for g in song["genres"]))[:3]
                listening_total = LISTENINGS_PER_PREMIUM if premium else random.randint(10, 50)
                activity = len(rated) + min(10, len(rated)) + min(3, len(rated)) + listening_total
                for days_ago in ([25, 15, 5] if premium else [5]):
                    formed_at = start + timedelta(days=90 - days_ago)
                    map_id = insert_id(cur, """
                        INSERT INTO public.musical_maps
                            (user_id, formed_at, listening_frequency, app_activity, mood)
                        VALUES (%s, %s, %s, %s, %s) RETURNING map_id
                    """, (user_id, formed_at, round(listening_total / 30, 4), activity, random.choice(moods)))
                    for position, song in enumerate(top_songs, 1):
                        cur.execute("""
                            INSERT INTO public.map_songs
                                (map_id, song_id, top_position, last_listened_at)
                            VALUES (%s, %s, %s, %s)
                        """, (map_id, song["id"], position, last_times.get(song["id"])))
                    for position, artist_id in enumerate(top_artists, 1):
                        cur.execute("INSERT INTO public.map_artists VALUES (%s, %s, %s)",
                                    (map_id, artist_id, position))
                    for position, genre_id in enumerate(top_genres, 1):
                        cur.execute("INSERT INTO public.map_genres VALUES (%s, %s, %s)",
                                    (map_id, genre_id, position))
                    add_action(cur, user_id, 1, "form", formed_at, map_id)
                if number % 10 == 0:
                    print(f"Обработано пользователей: {number}/{USER_COUNT}", flush=True)

    print(f"Готово: {USER_COUNT} пользователей, {ARTIST_COUNT} исполнителей, "
          f"{ALBUM_COUNT} альбомов, {SONG_COUNT} песен, {listening_count} прослушиваний.")


if __name__ == "__main__":
    try:
        main()
    except psycopg.Error as error:
        print(f"Ошибка PostgreSQL: {error}")
        raise SystemExit(1)
