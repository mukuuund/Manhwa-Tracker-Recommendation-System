def store_series_in_mysql(local):
#     conn = get_connection()
#     if not conn:
#         return
#     cursor = conn.cursor()
#     sql ="""
#     INSERT INTO series (title,canonical,local_latest_chapter,channel)
#     values (%s,%s,%s,%s)
#     ON DUPLICATE KEY UPDATE 
#     local_latest_chapter = GREATEST(local_latest_chapter, VALUES(local_latest_chapter)),
#     channel = VALUES(channel),"""