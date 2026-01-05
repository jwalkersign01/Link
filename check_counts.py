import sqlite3

conn = sqlite3.connect('linkedin_data.db')
cursor = conn.cursor()
cursor.execute("SELECT type, COUNT(*) FROM linkedin_data GROUP BY type")
rows = cursor.fetchall()
print(f"Counts: {rows}")
conn.close()
