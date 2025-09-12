# 📚 Manhwa Tracker Recommendation System (WIP)

A personal project for tracking your manhwa library and generating **personalized recommendations** using **Sentence-BERT embeddings**.  

This system connects to a **MySQL database** containing:
- `series` → your personal library  
- `manhwa_meta` → metadata (descriptions, genres, etc.)  
- `trending_manhwa` → pool of trending titles  

It recommends trending manhwa **similar to your library**, while **excluding any titles you’ve already read** (from `series` or `manhwa_meta`).

---

## 🚧 Project Status
⚠️ **Work In Progress**: Features and structure may change.  
Not ready for production use yet.

---

## ✨ Features
- Embeds library + trending manhwa using [`sentence-transformers`](https://www.sbert.net/).  
- Computes similarity with **cosine similarity on normalized embeddings**.  
- Excludes manhwa already present in your library or metadata tables.  
- Outputs:
  - Top-K recommendations **per library item**  
  - A pooled, unique list of recommendations across your library  

---

## 📂 Repository Structure
