CREATE TABLE IF NOT EXISTS series (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  canonical VARCHAR(255) NOT NULL,
  local_latest_chapter DECIMAL(10,3) NULL,
  channel VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP 
             ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_series_canonical (canonical),
  UNIQUE KEY uq_series_title (title)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;



CREATE TABLE IF NOT EXISTS manhwa_meta (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  search_title   VARCHAR(255) NULL,   
  display        VARCHAR(255) NULL,   
  status         VARCHAR(64) NULL,    
  chapters_total INT NULL,            
  genres         JSON NULL,           
  description    MEDIUMTEXT NULL,     
  updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;



CREATE TABLE IF NOT EXISTS trending_manhwa (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,


  canonical VARCHAR(255) NOT NULL,

  display VARCHAR(255) NOT NULL,
  site_url VARCHAR(512) NULL,

  average_score TINYINT UNSIGNED NULL,
  popularity INT UNSIGNED NULL,
  favourites INT UNSIGNED NULL,
  genres JSON NULL,
  chapters_total INT NULL,
  description MEDIUMTEXT NULL,

  source VARCHAR(32) NOT NULL DEFAULT 'anilist',

  last_trending_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  
  refreshed_on DATE NOT NULL DEFAULT (CURRENT_DATE),

  inserted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  UNIQUE KEY uq_trending_canonical (canonical)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;





CREATE TEMPORARY TABLE tmp_trending_stage (
  canonical VARCHAR(255) NOT NULL,
  display   VARCHAR(255) NOT NULL,
  site_url  VARCHAR(512) NULL,
  average_score TINYINT UNSIGNED NULL,
  popularity    INT UNSIGNED NULL,
  favourites    INT UNSIGNED NULL,
  genres        JSON NULL,
  chapters_total INT NULL,
  description   MEDIUMTEXT NULL,
  last_trending_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
