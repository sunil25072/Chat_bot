import re

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Add staticfiles import and mount
static_mount = """
from fastapi.staticfiles import StaticFiles
import os

os.makedirs("static/customer_images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

"""
if 'StaticFiles' not in text:
    text = text.replace('app = FastAPI()\n', 'app = FastAPI()\n' + static_mount)


# 2. Add DB setup and scraper loop
scraper_logic = """
import sqlite3
import asyncio
import os
import urllib.request
from bs4 import BeautifulSoup
from contextlib import closing

DB_FILE = "customers.db"

def init_db():
    with closing(sqlite3.connect(DB_FILE)) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS customers (
                    name TEXT PRIMARY KEY,
                    industry TEXT,
                    image_url TEXT,
                    local_image_path TEXT
                )
            ''')
        conn.commit()

def scrape_and_store_customers():
    print("Scraping customers and downloading images...")
    try:
        req = urllib.request.Request('https://systechusa.com/customers/', headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        
        tabs_container = soup.find(class_='et_pb_tabs_controls')
        content_container = soup.find(class_='et_pb_all_tabs')
        
        if not tabs_container or not content_container:
            return

        tab_links = tabs_container.find_all('a')
        tab_names = [a.text.strip() for a in tab_links]
        tab_divs = content_container.find_all(class_='et_pb_tab')
        
        with closing(sqlite3.connect(DB_FILE)) as conn:
            with closing(conn.cursor()) as cursor:
                for name, div in zip(tab_names, tab_divs):
                    if name.lower() == 'all':
                        continue
                    images = div.find_all('img')
                    for img in images:
                        alt = img.get('alt', '').strip()
                        src = img.get('src')
                        if not src:
                            continue
                            
                        if alt and len(alt) > 2 and alt.lower() not in ['logo', 'image', 'picture']:
                            clean_name = alt.title()
                        else:
                            raw_name = src.split('/')[-1].split('.')[0]
                            clean_name = raw_name.replace('-', ' ').replace('_', ' ').title().strip()
                            
                        if len(clean_name) <= 2 or clean_name.isdigit() or clean_name.lower() in ['logo', 'image', 'untitled', 'client', 'customer']:
                            continue
                            
                        # Download image if not exists
                        filename = src.split('/')[-1]
                        local_path = f"static/customer_images/{filename}"
                        if not os.path.exists(local_path):
                            try:
                                urllib.request.urlretrieve(src, local_path)
                            except Exception as e:
                                print(f"Failed to download image {src}: {e}")
                                local_path = ""
                                
                        cursor.execute('''
                            INSERT OR REPLACE INTO customers (name, industry, image_url, local_image_path)
                            VALUES (?, ?, ?, ?)
                        ''', (clean_name, name, src, local_path))
            conn.commit()
        print("Customer scraping complete.")
    except Exception as e:
        print(f"Failed to scrape customers: {e}")

async def scrape_customers_loop():
    while True:
        scrape_and_store_customers()
        await asyncio.sleep(3600)

@app.on_event("startup")
async def startup_event():
    init_db()
    asyncio.create_task(scrape_customers_loop())

def get_customers_from_db():
    try:
        with closing(sqlite3.connect(DB_FILE)) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("SELECT industry, name FROM customers ORDER BY industry, name")
                rows = cursor.fetchall()
                
                if not rows:
                    return "- Systech serves over 1,200 enterprise customers globally."
                    
                grouped = {}
                for industry, name in rows:
                    if industry not in grouped:
                        grouped[industry] = []
                    grouped[industry].append(name)
                    
                output_lines = []
                for ind, names in grouped.items():
                    output_lines.append(f"- **{ind}:** {', '.join(names)}")
                return "\\n".join(output_lines)
    except Exception as e:
        print(f"DB Error: {e}")
        return "- Systech serves over 1,200 enterprise customers globally."

"""

# Remove old fetch_dynamic_customers
text = re.sub(r'customer_cache = {"text": "", "last_fetched": 0}\s*def fetch_dynamic_customers\(\):.*?return "- Systech serves over 1,200 enterprise customers globally."\s*except Exception as e:\s*print\(f"Failed to scrape customers: \{e\}"\)\s*return "- Systech serves over 1,200 enterprise customers globally."\s*', '', text, flags=re.DOTALL)

# Insert the new logic before get_instructions
text = re.sub(r'def get_instructions\(\):', scraper_logic + '\ndef get_instructions():', text)

# Rewrite get_instructions to use the DB
old_get_instr = r'def get_instructions\(\):[\s\S]*?return BASE_INSTRUCTIONS\.replace\("{dynamic_customers}", customer_cache\["text"\]\)'
new_get_instr = """def get_instructions():
    customers_text = get_customers_from_db()
    return BASE_INSTRUCTIONS.replace("{dynamic_customers}", customers_text)"""

text = re.sub(old_get_instr, new_get_instr, text)


with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('app.py updated successfully!')
