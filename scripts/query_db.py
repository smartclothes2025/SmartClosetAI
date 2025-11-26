import psycopg2

try:
    conn = psycopg2.connect(
        host='127.0.0.1',
        user='postgres',
        password='cguim',
        database='closet'
    )
    cur = conn.cursor()
    
    cur.execute("SELECT id, name, category, cover_image_url FROM wardrobe_items WHERE cover_image_url IS NOT NULL LIMIT 5;")
    rows = cur.fetchall()
    
    print('Wardrobe items with valid image URLs:')
    for row in rows:
        print(f'\nID: {row[0]}')
        print(f'Name: {row[1]}')
        print(f'Category: {row[2]}')
        print(f'Image URL: {row[3]}')
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f'DB connection failed: {e}')
