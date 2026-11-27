// Browser-preview data (used only outside Qt). Same shape the Python service sends.
const it = (id, title, type, episodes, year, score, match, tags, reasons, studios, airing = false) => ({
  id, title, titleJp: title, img: "", score, type, episodes, year, tags, studios, match, reasons, airing,
  synopsis: "", url: `https://anilist.co/anime/${id}`, status: airing ? "Currently Airing" : "Finished Airing",
});
export const SAMPLE_RECS = {
  mode: "balanced", updatedAt: new Date().toISOString(),
  profile: { size: 508, rated: 309, mean: 8.1,
    topTags: ["Fantasy", "Action", "Adventure", "Comedy", "Drama", "Magic", "Isekai"], avoidTags: ["Ecchi", "Harem"] },
  items: [
    it(154587, "Frieren: Beyond Journey's End", "TV", 28, 2023, 9.3, 98, ["Fantasy", "Adventure", "Drama"], ["Fans of Mushishi and Violet Evergarden also liked this", "Matches your taste for Fantasy, Adventure"], ["Madhouse"]),
    it(101348, "Vinland Saga", "TV", 24, 2019, 8.8, 94, ["Action", "Drama", "Adventure"], ["Matches your taste for Action, Drama", "Rated 8.8/10 by fans"], ["Wit Studio"]),
    it(113415, "Jujutsu Kaisen", "TV", 24, 2020, 8.6, 91, ["Action", "Supernatural", "Fantasy"], ["Fans of Black Clover also liked this"], ["MAPPA"]),
    it(21, "ONE PIECE", "TV", null, 1999, 8.9, 88, ["Adventure", "Comedy", "Fantasy"], ["Airing right now"], ["Toei Animation"], true),
    it(20954, "A Silent Voice", "Movie", 1, 2016, 8.9, 84, ["Drama", "Romance"], ["Rated 8.9/10 by fans"], ["Kyoto Animation"]),
    it(97940, "Made in Abyss", "TV", 13, 2017, 8.6, 82, ["Adventure", "Fantasy", "Mystery"], ["A lesser-known gem with strong ratings"], ["Kinema Citrus"]),
    it(9253, "Steins;Gate", "TV", 24, 2011, 9.0, 79, ["Sci-Fi", "Thriller", "Drama"], ["Matches your taste for Drama"], ["White Fox"]),
    it(98314, "Mob Psycho 100", "TV", 12, 2016, 8.6, 74, ["Action", "Comedy", "Supernatural"], ["Matches your taste for Action, Comedy"], ["Bones"]),
  ],
};
