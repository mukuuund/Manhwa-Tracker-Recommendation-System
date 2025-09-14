import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from db import get_connection

conn = get_connection()

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
TOP_K_EACH = 5          # how many recs per library item
MAX_DESC_CHARS = 2000 

library_df = pd.read_sql(
    """
    SELECT
        s.id                    AS series_id,
        s.title                 AS series_title,
        s.canonical             AS series_canonical,
        s.user_preference       AS user_perf,
        s.local_latest_chapter  AS local_latest_chapter,
        s.telegram_latest_chapter AS telegram_latest_chapter,
        s.created_at            AS created_at,
        s.updated_at            AS updated_at,
        m.id                    AS meta_id,
        m.display               AS meta_display,
        m.description           AS meta_description,
        m.genres                AS meta_genres
    FROM series s
    LEFT JOIN manhwa_meta m
        ON LOWER(m.display) = LOWER(s.title)
    """,
    conn,
)

trending_df = pd.read_sql(
    """
    SELECT
        id,
        canonical,
        display AS title,
        description,
        genres,
        popularity,
        favourites,
        average_score
    FROM trending_manhwa
    """,
    conn,
)
conn.close()



def prep_text(title, desc, genres):
    title = (title or "").strip()
    desc  = (desc or "").strip().replace("\n", " ")
    genres = (genres or "").strip()
    if MAX_DESC_CHARS:
        desc = desc[:MAX_DESC_CHARS]

    parts = []
    if title:  parts.append(title)
    if desc:   parts.append(desc)
    if genres: parts.append(f"Genres: {genres}")

    return " — ".join(parts)



library_df["title_for_embed"] = library_df.apply(
    lambda r: (r["meta_display"] or r["series_title"] or "").strip(), axis=1
)
library_df["desc_for_embed"] = library_df["meta_description"].fillna("").astype(str)
library_df["text"] = library_df.apply(
    lambda r: prep_text(r["title_for_embed"], r["desc_for_embed"], r["meta_genres"]), axis=1
)
library_df = library_df[library_df['text'].str.len()>0].reset_index(drop=True)




trending_df["title"] = trending_df["title"].fillna("").astype(str).str.strip()
trending_df["description"] = trending_df["description"].fillna("").astype(str)
trending_df["text"] = trending_df.apply(
    lambda r: prep_text(r["title"], r["description"], r["genres"]), axis=1
)
trending_df = trending_df[trending_df["text"].str.len() > 0].reset_index(drop=True)
model = SentenceTransformer(MODEL_NAME)


lib_emb = model.encode(
    library_df['text'].tolist(),
    batch_size=64,
    show_progress_bar=True,
    normalize_embeddings=True
)

cand_emb = model.encode(
    trending_df['text'].tolist(),
    batch_size=64,
    show_progress_bar=True,
    normalize_embeddings=True
)
#print(lib_emb)


# Avoiding Duplicate Recommendation 
read_titles = set(library_df['title_for_embed'].str.lower())
red_canon = set(
    [c.lower() for c in library_df['series_canonical'].dropna().astype(str)]
) 

cand_title_lower = trending_df["title"].str.lower()
cand_canon_lower = trending_df["canonical"].fillna("").astype(str).str.lower()


already_read_mask = cand_title_lower.isin(read_titles) | cand_canon_lower.isin(red_canon)


sim_mat = lib_emb @ cand_emb.T # Dot Product 
# @ is matrix multiplication operation and .T is transpose of cand_emb 
# print(trending_df['description'])

# Set similarity of already-read items to very negative so they never get recommended
sim_mat[:, np.where(already_read_mask.values)[0]] = -1e9



W_GAP   = 0.30   # weight of chapter gap
W_FRESH = 0.50   # weight of freshness
W_PREF  = 0.20   # weight of user preference
TAU_UPD = 30.0   # days scale for updated_at (smaller => cares more about *very* recent updates)
TAU_NEW = 90.0   # days scale for created_at
ALPHA   = 0.50   # how strongly the final weight boosts similarity (0=no effect, 1=strong)

library_df["local_latest_chapter"]    = pd.to_numeric(library_df["local_latest_chapter"], errors="coerce")
library_df["telegram_latest_chapter"] = pd.to_numeric(library_df["telegram_latest_chapter"], errors="coerce")
library_df["created_at"]              = pd.to_datetime(library_df["created_at"], errors="coerce", utc=True)
library_df["updated_at"]              = pd.to_datetime(library_df["updated_at"], errors="coerce", utc=True)
library_df["user_perf"]               = library_df["user_perf"].fillna("neutral")

chapter_gap = (library_df['telegram_latest_chapter'].fillna(0) - library_df['local_latest_chapter'].fillna(0))
chapter_gap = chapter_gap.clip(lower=0) # sets the data lower that 0 to 0 and greater than 1 to 1
denom = library_df["telegram_latest_chapter"].fillna(1).replace(0, 1).abs()
gap_norm = (chapter_gap / denom).clip(0, 1)  # 0=no gap, 1=large relative gap



now = pd.Timestamp.utcnow()
days_since_upd = ((now - library_df["updated_at"]).dt.total_seconds() / 86400.0).fillna(365.0)
days_since_new = ((now - library_df["created_at"]).dt.total_seconds() / 86400.0).fillna(365.0)
fresh_upd = np.exp(-days_since_upd / TAU_UPD)
fresh_new = np.exp(-days_since_new / TAU_NEW)
freshness = 0.6 * fresh_upd + 0.4 * fresh_new 




pref_map = {"liked": 1.0, "neutral": 0.5, "unliked": 0.0}
pref_score = library_df["user_perf"].map(pref_map).fillna(0.5)


seed_weight = (W_GAP * gap_norm) + (W_FRESH * freshness) + (W_PREF * pref_score)
seed_weight = seed_weight.clip(0, 1).values

row_scale = (1.0 + ALPHA * seed_weight).reshape(-1, 1)
sim_mat = row_scale * sim_mat



def topk_for_row(row_idx,k=TOP_K_EACH):
    sims = sim_mat[row_idx]
    top_idx = np.argpartition(-sims, kth=min(k, sims.size-1))[:k]
    top_idx = top_idx[np.argsort(-sims[top_idx])]
    out = trending_df.loc[top_idx, ["id", "canonical", "title", "description", "genres", "popularity", "favourites", "average_score"]].copy()
    out["similarity"] = [float(sims[i]) for i in top_idx]
    out.insert(0, "based_on", library_df.loc[row_idx, "title_for_embed"])
    return out.reset_index(drop=True)

per_item_recs = []
pooled = []

for i in range(len(library_df)):
    rec_i = topk_for_row(i, TOP_K_EACH)
    per_item_recs.append(rec_i)
    pooled.append(rec_i.assign(source_row=i))

per_item_recs_df = pd.concat(per_item_recs, ignore_index=True)

# Pooled unique: keep the best similarity if a candidate appears for multiple library items
pooled_df = pd.concat(pooled, ignore_index=True)
pooled_best = (
    pooled_df
    .sort_values("similarity", ascending=False)
    .drop_duplicates(subset=["id", "canonical"], keep="first")
    .reset_index(drop=True)
)

print("\n=== Sample: Top-K per library title ===")
print(per_item_recs_df.head(20))
print(per_item_recs_df['title'].head(20))

print("\n=== Pooled unique recommendations (best across your whole library) ===")
print(pooled_best.head(30))
print(pooled_best['title'].head(30))







