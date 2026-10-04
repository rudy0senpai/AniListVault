-- AnimeVault export
-- Schema + data. Import restores this into a temporary database
-- first, so it never executes against the live library.

CREATE TABLE anime (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    title    TEXT    NOT NULL,
    title_ja TEXT,
    episodes INTEGER DEFAULT 0,
    status   TEXT    NOT NULL DEFAULT 'plan_to_watch',
    score    REAL,
    notes    TEXT    DEFAULT ''
, tier TEXT, rewatches INTEGER DEFAULT 0, episodes_watched INTEGER DEFAULT 0, favorite INTEGER DEFAULT 0, first_watched TEXT DEFAULT '', last_watched TEXT DEFAULT '', completed_date TEXT DEFAULT '', privacy TEXT DEFAULT 'public');
CREATE TABLE anime_metadata (
    anime_id            INTEGER PRIMARY KEY,
    title_en            TEXT    DEFAULT '',
    synopsis            TEXT    DEFAULT '',
    media_type          TEXT    DEFAULT '',
    airing_status       TEXT    DEFAULT '',
    genres              TEXT    DEFAULT '',
    studios             TEXT    DEFAULT '',
    aired_from          TEXT    DEFAULT '',
    aired_to            TEXT    DEFAULT '',
    season              TEXT    DEFAULT '',
    season_year         INTEGER,
    duration            INTEGER DEFAULT 0,
    poster_url          TEXT    DEFAULT '',
    poster_path         TEXT    DEFAULT '',
    mal_id              INTEGER,
    anilist_id          INTEGER,
    kitsu_id            TEXT    DEFAULT '',
    tmdb_id             INTEGER,
    source_provider     TEXT    DEFAULT '',
    metadata_fetched_at TEXT    DEFAULT '', anidb_id INTEGER,
    FOREIGN KEY (anime_id) REFERENCES anime(id) ON DELETE CASCADE
);
CREATE TABLE literature (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    category         TEXT    NOT NULL DEFAULT 'manga',
    title            TEXT    NOT NULL,
    title_native     TEXT    DEFAULT '',
    synonyms         TEXT    DEFAULT '',
    format           TEXT    DEFAULT '',
    status           TEXT    NOT NULL DEFAULT 'watching',
    tier             TEXT,
    rewatches        INTEGER DEFAULT 0,
    chapters_read    INTEGER DEFAULT 0,
    chapters         INTEGER DEFAULT 0,
    volumes          INTEGER DEFAULT 0,
    volumes_read     INTEGER DEFAULT 0,
    favorite         INTEGER DEFAULT 0,
    notes            TEXT    DEFAULT '',
    first_read       TEXT    DEFAULT '',
    last_read        TEXT    DEFAULT '',
    completed_date   TEXT    DEFAULT '',
    privacy          TEXT    DEFAULT 'public',
    origin_country   TEXT    DEFAULT ''
);
CREATE TABLE literature_metadata (
    literature_id     INTEGER PRIMARY KEY,
    title_en          TEXT DEFAULT '',
    synopsis          TEXT DEFAULT '',
    genres            TEXT DEFAULT '',
    authors           TEXT DEFAULT '',
    artists           TEXT DEFAULT '',
    serialization     TEXT DEFAULT '',
    pub_status        TEXT DEFAULT '',
    started_at        TEXT DEFAULT '',
    ended_at          TEXT DEFAULT '',
    cover_url         TEXT DEFAULT '',
    cover_path        TEXT DEFAULT '',
    anilist_id        INTEGER,
    kitsu_id          TEXT DEFAULT '',
    mal_id            INTEGER,
    source_provider   TEXT DEFAULT '',
    metadata_fetched_at TEXT DEFAULT '',
    FOREIGN KEY (literature_id) REFERENCES literature(id) ON DELETE CASCADE
);
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX idx_anime_status ON anime(status);
CREATE INDEX idx_anime_title ON anime(title);
CREATE INDEX idx_lit_anilist ON literature_metadata(anilist_id);
CREATE INDEX idx_lit_category ON literature(category);
CREATE INDEX idx_lit_tier ON literature(tier);
CREATE INDEX idx_lit_title ON literature(title);
CREATE INDEX idx_metadata_anilist_id ON anime_metadata(anilist_id);
CREATE INDEX idx_metadata_kitsu_id ON anime_metadata(kitsu_id);
CREATE INDEX idx_metadata_mal_id ON anime_metadata(mal_id);
CREATE INDEX idx_metadata_tmdb_id ON anime_metadata(tmdb_id);

BEGIN TRANSACTION;
INSERT INTO anime (title, title_ja, episodes, status, score, notes, tier, rewatches, episodes_watched, favorite, first_watched, last_watched, completed_date, privacy) VALUES ('NARUTO', 'NARUTO -ナルト-', 220, 'completed', 'NULL', NULL, 'SS', 0, 220, 1, NULL, NULL, NULL, 'public');
INSERT INTO anime_metadata (anime_id, title_en, synopsis, media_type, genres, studios, aired_from, aired_to, season, season_year, duration, poster_path, mal_id, anilist_id, kitsu_id, tmdb_id, source_provider, metadata_fetched_at) VALUES (last_insert_rowid(), 'Naruto', 'Naruto Uzumaki, a hyperactive and knuckle-headed ninja, lives in Konohagakure, the Hidden Leaf village. Moments prior to his birth, a huge demon known as the Kyuubi, the Nine-tailed Fox, attacked Konohagakure and wreaked havoc. In order to put an end to the Kyuubi''s rampage, the leader of the village, the 4th Hokage, sacrificed his life and sealed the monstrous beast inside the newborn Naruto. 
Shunned because of the presence of the Kyuubi inside him, Naruto struggles to find his place in the village. He strives to become the Hokage of Konohagakure, and he meets many friends and foes along the way. 
(Source: MAL Rewrite)', 'TV', '["Action", "Adventure", "Comedy", "Drama", "Fantasy", "Supernatural"]', '["Studio Pierrot"]', '2002-10-03', '2007-02-08', 'FALL', 2002, 23, 'C:\Users\Rudy0senpai\AppData\Roaming\AnimeVault\posters\poster_d32a699070c937eaa03b07f4.jpg', 20, 20, NULL, NULL, 'anilist', '2026-10-03T09:40:18.866124+00:00');
INSERT INTO anime (title, title_ja, episodes, status, score, notes, tier, rewatches, episodes_watched, favorite, first_watched, last_watched, completed_date, privacy) VALUES ('ONE PIECE', 'ONE PIECE', 1180, 'watching', 'NULL', NULL, 'SSS', 0, 1180, 1, NULL, NULL, NULL, 'public');
INSERT INTO anime_metadata (anime_id, title_en, synopsis, media_type, genres, studios, aired_from, aired_to, season, season_year, duration, poster_path, mal_id, anilist_id, kitsu_id, tmdb_id, source_provider, metadata_fetched_at) VALUES (last_insert_rowid(), 'ONE PIECE', 'Gold Roger was known as the Pirate King, the strongest and most infamous being to have sailed the Grand Line. The capture and death of Roger by the World Government brought a change throughout the world. His last words before his death revealed the location of the greatest treasure in the world, One Piece. It was this revelation that brought about the Grand Age of Pirates, men who dreamed of finding One Piece (which promises an unlimited amount of riches and fame), and quite possibly the most coveted of titles for the person who found it, the title of the Pirate King.
Enter Monkey D. Luffy, a 17-year-old boy that defies your standard definition of a pirate. Rather than the popular persona of a wicked, hardened, toothless pirate who ransacks villages for fun, Luffy’s reason for being a pirate is one of pure wonder; the thought of an exciting adventure and meeting new and intriguing people, along with finding One Piece, are his reasons of becoming a pirate. Following in the footsteps of his childhood hero, Luffy and his crew travel across the Grand Line, experiencing crazy adventures, unveiling dark mysteries and battling strong enemies, all in order to reach One Piece.
*This includes the following special episodes:
- Chopperman to the Rescue! Protect the TV Station by the Shore! (Episode 336)
- The Strongest Tag-Team! Luffy and Toriko''s Hard Struggle! (Episode 492)
- Team Formation! Save Chopper (Episode 542)
- History''s Strongest Collaboration vs. Glutton of the Sea (Episode 590)
- 20th Anniversary! Special Romance Dawn (Episode 907)', 'TV', '["Action", "Adventure", "Comedy", "Drama", "Fantasy"]', '["Toei Animation"]', '1999-10-20', NULL, 'FALL', 1999, 24, 'C:\Users\Rudy0senpai\AppData\Roaming\AnimeVault\posters\poster_d4ca8f33a0bf5c1efe105554.jpg', 21, 21, NULL, NULL, 'anilist', '2026-10-01T18:49:19.173742+00:00');
INSERT INTO literature (category, title, title_native, synonyms, format, status, tier, rewatches, chapters_read, chapters, volumes, favorite, notes, first_read, last_read, completed_date, privacy, origin_country) VALUES ('manga', 'ONE PIECE', 'ONE PIECE', '["원피스", "וואן פיס", "One Piece - Большой куш", "ワンピース", "ONE PIECE～航海王～", "วันพีซ"]', 'MANGA', 'watching', 'SSS', 0, 1180, 1180, 0, 1, NULL, NULL, NULL, NULL, 'public', 'JP');
INSERT INTO literature_metadata (literature_id, title_en, synopsis, genres, authors, artists, started_at, ended_at, cover_path, anilist_id, kitsu_id, mal_id, source_provider, metadata_fetched_at) VALUES (last_insert_rowid(), 'One Piece', 'As a child, Monkey D. Luffy was inspired to become a pirate by listening to the tales of the buccaneer "Red-Haired" Shanks. But his life changed when Luffy accidentally ate the Gum-Gum Devil Fruit and gained the power to stretch like rubber...at the cost of never being able to swim again! Years later, still vowing to become the king of the pirates, Luffy sets out on his adventure...one guy alone in a rowboat, in search of the legendary "One Piece," said to be the greatest treasure in the world...

(Source: VIZ Media)', '["Action", "Adventure", "Comedy", "Fantasy", "Curses", "Matriarchy", "Aromantic", "Shapeshifting", "Body Swapping", "Arranged Marriage", "Aliens", "Angels", "Artificial Intelligence", "Gender Bending", "Clone", "Bar", "Unrequited Love", "Dinosaurs", "Centaur", "Ninja"]', '["Eiichirou Oda"]', NULL, '1997-07-22', NULL, 'C:\Users\Rudy0senpai\AppData\Roaming\AnimeVault\posters\poster_06a88e5433bfdeeefdf4be1b.jpg', 30013, NULL, 13, 'anilist', NULL);
INSERT INTO literature (category, title, title_native, synonyms, format, status, tier, rewatches, chapters_read, chapters, volumes, favorite, notes, first_read, last_read, completed_date, privacy, origin_country) VALUES ('manga', 'Tonikaku Kawaii', 'トニカクカワイイ', '["Tonikaku Cawaii", "Generally Cute", "จะยังไงภรรยาของผมก็น่ารัก", "Fly me to the moon - Tóm lại là em dễ thương, được chưa?", "總之就是很可愛", "总之就是非常可爱", "Così carina. Fly me to the moon", "Beni Ay''a Götür"]', 'MANGA', 'on_hold', 'S', 0, 300, 361, 0, 1, NULL, NULL, NULL, NULL, 'public', 'JP');
INSERT INTO literature_metadata (literature_id, title_en, synopsis, genres, authors, artists, started_at, ended_at, cover_path, anilist_id, kitsu_id, mal_id, source_provider, metadata_fetched_at) VALUES (last_insert_rowid(), 'Fly Me to the Moon', 'First comes marriage, then comes an earthbound love that is out of this world! From the day his parents named him, Nasa Yuzaki has been destined for outer space…or so he believes. But while trying to join the space program, he is thrown for a loop when an accident introduces him to Tsukasa, a mysterious girl with strange powers. Is she an alien, a moon goddess or something else? Since she insists on marrying him, Nasa has plenty of chances to find out!

(Source: VIZ Media)

Notes: The 16th volume includes the 4 chapter prequel "FLY ME TO THE MOON".', '["Comedy", "Romance", "Slice of Life", "Software Development", "Maids", "Swordplay", "Otaku Culture", "Mythology", "Ojou-sama", "Tsundere", "Astronomy", "Parody", "Meta", "Primarily Adult Cast", "Shounen", "Coming of Age", "Amnesia", "Age Gap", "Historical", "Family Life"]', '["Kenjirou Hata"]', NULL, '2018-02-14', NULL, 'C:\Users\Rudy0senpai\AppData\Roaming\AnimeVault\posters\poster_4cac978a08d20be05c0fbc0f.png', 101177, NULL, 112589, 'anilist', NULL);
INSERT INTO literature (category, title, title_native, synonyms, format, status, tier, rewatches, chapters_read, chapters, volumes, favorite, notes, first_read, last_read, completed_date, privacy, origin_country) VALUES ('manhua', 'Cong Jintian Kaishi Dang Chengzhu', '从今天开始当城主', '["Starting From Today I''ll Work As A City Lord", "오늘부터 성주"]', 'MANGA', 'on_hold', 'A', 0, 520, 551, 0, 0, NULL, NULL, NULL, NULL, 'public', 'CN');
INSERT INTO literature_metadata (literature_id, title_en, synopsis, genres, authors, artists, started_at, ended_at, cover_path, anilist_id, kitsu_id, mal_id, source_provider, metadata_fetched_at) VALUES (last_insert_rowid(), 'Become the Castellan in Another World', 'When a gamer and homebody starts the BUFF for traveling through time and space, he certainly chooses to make waves! Make waves! And make waves! Domineering cat lady, Lori fox lady, Girly rabbit lady…This is not a Zoo! This is a fantastic Another World under the rule of the law of the jungle! In a real strategic game and a huge conspiracy crisis, the Overlord of Another World is emerging, with the rest nothing but losers…

(Source: Webnovel)', '["Comedy", "Fantasy", "Kemonomimi", "Crossover", "Male Protagonist", "Kingdom Management", "Full Color", "Female Harem", "Economics", "Isekai"]', '["Junxin Shanmu"]', '["Lou Xiao Yue Tiantian Bu Gaoxing"]', '2019-01-01', NULL, 'C:\Users\Rudy0senpai\AppData\Roaming\AnimeVault\posters\poster_d0e0805a839b8a244edb9a06.png', 118368, NULL, NULL, 'anilist', NULL);
INSERT INTO literature (category, title, title_native, synonyms, format, status, tier, rewatches, chapters_read, chapters, volumes, favorite, notes, first_read, last_read, completed_date, privacy, origin_country) VALUES ('manhua', 'Haksageomjeon', '학사검전', '["Records of the Swordsman Scholar"]', 'MANGA', 'watching', 'A', 0, 218, 218, 0, 0, NULL, NULL, NULL, NULL, 'public', 'KR');
INSERT INTO literature_metadata (literature_id, title_en, synopsis, genres, authors, artists, started_at, ended_at, cover_path, anilist_id, kitsu_id, mal_id, source_provider, metadata_fetched_at) VALUES (last_insert_rowid(), NULL, 'Scholar Woon Hyun enters the palace after passing the Imperial Examination. Though he soon comes to lament his poor and miserable life of having to deal with the Crown Prince''s hobbies, despite that, he doesn''t give up and tries his best to learn martial arts. But Woon Hyun suddenly picks up his brush to conquer the Murim?! The hidden story of the scholar who passed the Imperial Examination at a young age begins.(Source: KakaoPage, translated)', '["Action", "Fantasy", "Full Color", "Time Skip", "Male Protagonist", "Wuxia", "Swordplay", "Martial Arts", "Writing", "Primarily Adult Cast", "Politics", "Historical"]', '["Geobalhan"]', '["Sung-Woo Park"]', '2022-06-05', NULL, 'C:\Users\Rudy0senpai\AppData\Roaming\AnimeVault\posters\poster_95ec1c56b5530ed87ef2d09d.png', 151220, NULL, 159005, 'anilist', NULL);
INSERT INTO literature (category, title, title_native, synonyms, format, status, tier, rewatches, chapters_read, chapters, volumes, favorite, notes, first_read, last_read, completed_date, privacy, origin_country) VALUES ('manhua', 'Zhe Yi Shi Wo Yao Dang Zhi Zun', '这一世我要当至尊', '["万古至尊", "The Ultimate Of All Ages", "The Ancient Sovereign of Eternity", "The Eternal Supreme", "Still Supreme in My Second Life", "만고지존", "二度目の人生俺は至尊になる"]', 'MANGA', 'on_hold', 'SS', 0, 540, 570, 0, 1, NULL, NULL, NULL, NULL, 'public', 'CN');
INSERT INTO literature_metadata (literature_id, title_en, synopsis, genres, authors, artists, started_at, ended_at, cover_path, anilist_id, kitsu_id, mal_id, source_provider, metadata_fetched_at) VALUES (last_insert_rowid(), 'Rebirth Of The Ultimate Master', 'What happens when a former martial emperor gets reborn into a complete loser''s body? Gu Feiyang, a legendary martial artist who was ranked third-strongest in the continent, finds himself in this predicament when he wakes up in the body of 15-year-old Li Yunxiao. Li Yunxiao was once a failure who had yet to open a single chakra portal in his body, but now he''s morphed into a genius martial artist overnight and becomes the talk (and target) of the town. Armed with the expertise of his former life, Li Yunxiao is on a mission to complete the ultimate incantation that killed him in the first place - all while wiping the floor with his former bullies at school. Will he be able to exceed the accomplishments of his previous life? One thing''s for certain: no one will ever call him a loser again!

(Source: Tappytoon, edited)


Note: The title of the manhua changed from 万古至尊 to 这一世我要当至尊 starting from Ch. 14.', '["Action", "Adventure", "Comedy", "Fantasy", "Politics", "Cultivation", "Male Protagonist", "Reincarnation", "Martial Arts", "Age Regression", "Female Harem", "Full Color", "Wuxia", "Swordplay", "Alchemy"]', '["Di Shui"]', '["Jie Ke Nuo Wei"]', '2021-05-31', NULL, 'C:\Users\Rudy0senpai\AppData\Roaming\AnimeVault\posters\poster_b17aaa1c93160b6caf8d0f44.jpg', 138726, NULL, NULL, 'anilist', NULL);
INSERT INTO literature (category, title, title_native, synonyms, format, status, tier, rewatches, chapters_read, chapters, volumes, favorite, notes, first_read, last_read, completed_date, privacy, origin_country) VALUES ('manhwa', 'Lookism', '외모지상주의', '["外見至上主義", "APARI3NCIAS"]', 'MANGA', 'watching', 'SS', 0, 527, 527, 0, 1, NULL, NULL, NULL, NULL, 'public', 'KR');
INSERT INTO literature_metadata (literature_id, title_en, synopsis, genres, authors, artists, started_at, ended_at, cover_path, anilist_id, kitsu_id, mal_id, source_provider, metadata_fetched_at) VALUES (last_insert_rowid(), 'Lookism', 'Daniel is an unattractive loner who wakes up in a different body. Now tall, handsome, and cooler than ever in his new form, Daniel aims to achieve everything he couldn''t before. How far will he go to keep his body... and his secrets?(Source: WEBTOON)', '["Action", "Comedy", "Drama", "Supernatural", "Memory Manipulation", "Gambling", "LGBTQ+ Themes", "Homeless", "Detective", "Drugs", "Parody", "Cult", "Primarily Teen Cast", "Love Triangle", "Primarily Male Cast", "Meta", "Fashion", "Found Family", "Boxing", "Surreal Comedy"]', '["Tae-Jun Park"]', NULL, '2014-11-20', NULL, 'C:\Users\Rudy0senpai\AppData\Roaming\AnimeVault\posters\poster_bf575cb960e1f4828d502631.jpg', 86848, NULL, 111202, 'anilist', NULL);
INSERT INTO literature (category, title, title_native, synonyms, format, status, tier, rewatches, chapters_read, chapters, volumes, favorite, notes, first_read, last_read, completed_date, privacy, origin_country) VALUES ('manhwa', 'Solo Leveling', '나 혼자만 레벨업', '["I Level Up Alone", "Only I Level Up", "俺だけレベルアップな件", "我獨自升級", "Ore dake Level Up na Ken", "Поднятие уровня в одиночку", "Тільки я візьму новий рівень", "Вебтун. Поднятие уровня в одиночку. Solo Leveling"]', 'MANGA', 'completed', 'S', 0, 201, 201, 15, 0, NULL, NULL, NULL, NULL, 'public', 'KR');
INSERT INTO literature_metadata (literature_id, title_en, synopsis, genres, authors, artists, started_at, ended_at, cover_path, anilist_id, kitsu_id, mal_id, source_provider, metadata_fetched_at) VALUES (last_insert_rowid(), 'Solo Leveling', 'In a world where awakened beings called “Hunters” must battle deadly monsters to protect humanity, Seong Jin-U, nicknamed “the weakest hunter of all mankind,” finds himself in a constant struggle for survival. One day, after a brutal encounter in an overpowered dungeon wipes out his party and threatens to end his life, a mysterious System chooses him as its sole player: Jin-U has been granted the rare opportunity to level up his abilities, possibly beyond any known limits. Follow Jin-U’s journey as he takes on ever-stronger enemies, both human and monster, to discover the secrets deep within the dungeons and the ultimate extent of his powers.

(Source: Tappytoon)

Note: Includes 22 extra chapters.', '["Action", "Adventure", "Fantasy", "Marriage", "Snowscape", "Bullying", "Time Skip", "Language Barrier", "Estranged Family", "Chimera", "Assassins", "Heterosexual", "Age Regression", "Time Manipulation", "Anti-Hero", "Foreign", "Memory Manipulation", "Tragedy", "Video Games", "Post-Apocalyptic"]', NULL, '["Seong-Rak Jang"]', '2018-03-04', '2023-05-31', 'C:\Users\Rudy0senpai\AppData\Roaming\AnimeVault\posters\poster_00ab355cbac5cae6a0a5c88f.jpg', 105398, NULL, 121496, 'anilist', NULL);
INSERT INTO literature (category, title, title_native, synonyms, format, status, tier, rewatches, chapters_read, chapters, volumes, favorite, notes, first_read, last_read, completed_date, privacy, origin_country) VALUES ('manhwa', 'The Greatest Estate Developer', '역대급 영지 설계사', '["The World''s Best Engineer", "The Greatest Estate Designer", "El mejor desarrollador inmobiliario", "史詩級領地設計師", "史上最高の領地設計士", "史诗级领地设计师", "ยอดสถาปนิกผู้พิทักษ์อาณาจักร", "Niezrównany Inżynier"]', 'MANGA', 'completed', 'SSS', 0, 222, 222, 0, 1, NULL, NULL, NULL, NULL, 'public', 'KR');
INSERT INTO literature_metadata (literature_id, title_en, synopsis, genres, authors, artists, started_at, ended_at, cover_path, anilist_id, kitsu_id, mal_id, source_provider, metadata_fetched_at) VALUES (last_insert_rowid(), 'The Greatest Estate Developer', 'When civil engineering student Su-Ho Kim falls asleep reading a fantasy novel, he wakes up as a character in the book! Su-Ho is now in the body of Lloyd Frontera, a lazy noble who loves to drink, and whose family is in a mountain of debt. Using his engineering knowledge, Su-Ho designs inventions to avert the terrible future that lies in wait for him. With the help of a giant hamster, a knight, and the world’s magic, can Su-Ho dig his new family out of debt and build a better future?
(Source: WEBTOON, edited)
Note: Includes 12 extra chapters.', '["Adventure", "Comedy", "Fantasy", "Chimera", "Desert", "Mermaid", "Tomboy", "Crossdressing", "Class Struggle", "Heterosexual", "Military", "Necromancy", "Zombie", "Elf", "Cult", "Swordplay", "Reverse Isekai", "Butler", "Agriculture", "Dragons"]', '["Hyeon-Min Lee"]', '["Hyeon-Su Kim"]', '2021-08-05', '2026-01-01', 'C:\Users\Rudy0senpai\AppData\Roaming\AnimeVault\posters\poster_cd0fee7590057363134bb510.png', 140407, NULL, 147272, 'anilist', NULL);

COMMIT;
