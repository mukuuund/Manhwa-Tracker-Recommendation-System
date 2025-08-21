import os
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

load_dotenv()  # load credentials from .env

def get_connection():
    try:
        conn = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST", "localhost"),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DB")
        )
        return conn
    except Error as e:
        print(f"❌ MySQL connection error: {e}")
        return None