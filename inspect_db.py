import sqlite3
import json

conn = sqlite3.connect('linkedin_data.db')
cursor = conn.cursor()
cursor.execute("SELECT type, full_data FROM linkedin_data WHERE type='Company' LIMIT 5")
rows = cursor.fetchall()

for row in rows:
    print(f"\nType: {row[0]}")
    data = json.loads(row[1])
    print(f"Keys: {list(data.keys())}")
    print(f"Industry: {data.get('industry')}")
    print(f"Size: {data.get('employeeSize')}")
    print(f"HQ: {data.get('headquarters')}")

conn.close()
