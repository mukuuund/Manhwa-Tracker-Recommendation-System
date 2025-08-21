# 📚 Manhwa Tracker Recommendation System (WIP)

⚠️ **Status:** This project is currently under active development.  
Features and structure may change frequently. Not ready for production use yet.

---

## 🚀 Project Overview
The goal of this project is to build a **Manhwa Recommendation & Tracking System** that combines:
- 📥 **Telegram Downloads** → Track last and latest chapters downloaded from Telegram channels.  
- 🎭 **AniList Data** → Fetch top trending manhwas (titles, genres, descriptions).  
- ❤️ **User Preferences** → Support liked and uninterested manhwas.  
- 🧮 **Recommendation Engine** → Suggest manhwas based on:  
  - Chapter availability (latest vs local)  
  - Release frequency  
  - Genre/description similarity  
  - User preferences  

---

## 🛠️ Tech Stack
- **Python 3.10+**
- **MySQL** (for storing metadata & chapters)  
- **Telethon** (Telegram scraping)  
- **AniList API** (external manhwa data)  
- **scikit-learn / TensorFlow (planned)** for recommendation engine  

---

## 📌 Current Progress
- [x] Database schema for series & metadata  
- [x] Script to fetch chapter info from Telegram  
- [ ] Integration with AniList API  
- [ ] Recommendation model (sklearn/TensorFlow)  
- [ ] Web dashboard / CLI  

---

## 🗂️ Project Structure
