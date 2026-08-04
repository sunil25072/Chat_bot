from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

from fastapi.staticfiles import StaticFiles
import os

os.makedirs("static/customer_images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")





# Allow CORS so the frontend can call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
from dotenv import load_dotenv

load_dotenv()

# 1. Initialize Azure OpenAI client
try:
    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint="https://systechinternalapp.openai.azure.com/",
        api_version="2024-12-01-preview"
    )
except Exception as e:
    print(f"Error initializing Azure OpenAI client: {e}")
    client = None

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

import time

BASE_INSTRUCTIONS = """You are a friendly, helpful, and enthusiastic AI bot exclusively for Systech Solutions (systechusa.com) 👋.

Your ONLY purpose is to answer questions about Systech Solutions — services, products, partnerships, industries, case studies, etc.

IMPORTANT: You now have two tools at your disposal: `search_website` and `fetch_url`.
1. Use `search_website` when the user asks a specific question and you don't know the exact URL (e.g., "Do you have a Snowflake partnership?", "Who is the CEO?"). It will return a list of relevant page URLs.
2. Use `fetch_url` to read the specific URL you found, or if you already know the exact URL.
3. NEVER use `search_website` or `fetch_url` to find lists of customers or clients! You already have the complete list in the 'IMPORTANT CLIENT INFORMATION' section below. Just read the list!

CRITICAL SEARCH RULE:
When searching for specific people, authors, webinars, case studies, or blogs, you must search fully and robustly!
1. If the user asks about ANY person using only a first name or partial name (e.g., "Hari", "Sunil"), you MUST fetch the Leadership Team page (https://systechusa.com/leadership-team/) FIRST. Read the page to find their full name and details before deciding you don't know who they are.
2. If they are not on the leadership page, or if you are looking for an article or webinar they did, ALWAYS use the `search_website` tool with just their name (e.g., "Hari").
3. DO NOT add words like "webinar" or "article" to the `search_website` query (e.g., do not search "Hari webinar"), as the search API will fail to find it. Search ONLY the person's name!
4. DO NOT just read the titles returned by `search_website` and give up! You MUST use the `fetch_url` tool to read the actual content of the top returned links to see if the person or topic is mentioned inside the page.
5. DO NOT just check generic index pages like `/webinars/` or `/blog/`. You must search and read specific pages.

CRITICAL LEADERSHIP RULE: 
If the user asks about the CEO, you MUST list ALL CEOs. For Systech Solutions, both Srini Ramaswami and Arun Gollapudi are Co-Founder & CEOs. Do NOT say Arun is the COO. They are BOTH CEOs. If asked about the CEO, list both.
Additionally, if the user asks about ANY specific person by name (e.g. Balaji, Yusuf, Sunil, Keerthana, etc.) or asks about executives, you MUST use `fetch_url` on the Leadership Team page (https://systechusa.com/leadership-team/) FIRST to see if they are listed there!

Common pages you can check:
- Careers / Job Openings: https://systechusa.com/careers/
  *(CRITICAL RULE FOR CAREERS: You must look for the "OPEN ROLES" table. If the page says "No open roles found.", you MUST simply reply that there are no current job openings. Do NOT list the example roles under Practice Areas under any circumstances.)*
- About Us: https://systechusa.com/about-us/
- Leadership Team: https://systechusa.com/leadership-team/
- Services: https://systechusa.com/services/
- Contact: https://systechusa.com/contact-us/
- Data Engineering: https://systechusa.com/data-engineering-services/

IMPORTANT CLIENT INFORMATION:
If the user asks about clients, customers, or who we work with (either generally or in a specific sector like Banking, Gaming, Retail, etc.), you MUST provide the specific company names from the lists below. 
DO NOT use the `search_website` or `fetch_url` tools to look for customers! You already have the complete, official list of customers right here in your instructions. Just list the names from the text below:

{dynamic_customers}

Do NOT mention NDAs or confidentiality anymore, because these logos are explicitly published on the website. Just list out the relevant names!

Response Guidelines:
1. Tone: Warm, friendly, approachable, and professional. Use happy emojis!
2. Length: Medium length. Break down ideas into concise sentences and easy-to-read bullet lists.
3. Formatting: 
   - NEVER use special characters like "//", "###", or "####" for headers. Instead, just use **Bold Text** for your headings.
   - Always use bullet points or numbered lists when listing points, features, or items.
   - At the very end of your message, you MUST include a 'Sources' section with markdown links to the specific pages you got the information from (e.g. **Source:** [Page Title](URL)).
"""

customer_cache = {"text": "", "last_fetched": 0}

def fetch_dynamic_customers():
    try:
        import urllib.request
        from bs4 import BeautifulSoup
        
        req = urllib.request.Request('https://systechusa.com/customers/', headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        
        output_lines = []
        tabs_container = soup.find(class_='et_pb_tabs_controls')
        content_container = soup.find(class_='et_pb_all_tabs')
        
        if tabs_container and content_container:
            tab_links = tabs_container.find_all('a')
            tab_names = [a.text.strip() for a in tab_links]
            tab_divs = content_container.find_all(class_='et_pb_tab')
            
            for name, div in zip(tab_names, tab_divs):
                if name.lower() == 'all':
                    continue
                images = div.find_all('img')
                filenames = []
                for img in images:
                    # Try to use ALT text first, if it exists and is descriptive
                    alt = img.get('alt', '').strip()
                    if alt and len(alt) > 2 and alt.lower() not in ['logo', 'image', 'picture']:
                        clean_name = alt.title()
                    else:
                        # Fallback to filename
                        src = img.get('src')
                        if src:
                            raw_name = src.split('/')[-1].split('.')[0]
                            # Cleanup: replace hyphens/underscores with space, convert to title case
                            clean_name = raw_name.replace('-', ' ').replace('_', ' ').title().strip()
                        else:
                            continue
                            
                    # Smart Filter: Ignore names that are just numbers (like "1"), too short, or generic words
                    if len(clean_name) <= 2 or clean_name.isdigit() or clean_name.lower() in ['logo', 'image', 'untitled', 'client', 'customer']:
                        continue
                        
                    filenames.append(clean_name)
                if filenames:
                    output_lines.append(f"- **{name}:** {', '.join(filenames)}")
                    
        return "\n".join(output_lines) if output_lines else "- Systech serves over 1,200 enterprise customers globally."
    except Exception as e:
        print(f"Failed to scrape customers: {e}")
        return "- Systech serves over 1,200 enterprise customers globally."


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
                                img_req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0'})
                                img_data = urllib.request.urlopen(img_req, timeout=10).read()
                                with open(local_path, 'wb') as img_file:
                                    img_file.write(img_data)
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
                return "\n".join(output_lines)
    except Exception as e:
        print(f"DB Error: {e}")
        return "- Systech serves over 1,200 enterprise customers globally."


def get_instructions():
    customers_text = get_customers_from_db()
    return BASE_INSTRUCTIONS.replace("{dynamic_customers}", customers_text)

def extract_urls(text):
    import re
    url_pattern = re.compile(r'https?://[^\s]+')
    return url_pattern.findall(text)

def fetch_url_text(url):
    if "customers" in url.lower() and "systechusa" in url.lower():
        return "SYSTEM ERROR: DO NOT FETCH THE CUSTOMERS PAGE! You must use the exact list below to answer the user:\n\n" + get_customers_from_db()
    try:
        import urllib.request
        from bs4 import BeautifulSoup
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove unwanted elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.extract()
            
        text = soup.get_text(separator=' ', strip=True)
        # Limit to first 6000 characters to prevent hitting token limits
        return text[:6000]
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return ""

def search_website(query):
    q_lower = query.lower()
    if "customer" in q_lower or "client" in q_lower or any(ind in q_lower for ind in ["gaming", "retail", "banking", "health", "finance", "education", "manufacturing", "media", "utilities", "automotive"]):
        return "SYSTEM ERROR: DO NOT SEARCH THE WEB FOR CUSTOMER LISTS! You must use the exact list below to answer the user:\n\n" + get_customers_from_db()
    try:
        import urllib.request, urllib.parse, json
        q = urllib.parse.quote(query)
        req = urllib.request.Request(f'https://systechusa.com/wp-json/wp/v2/search?search={q}', headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
        results = []
        for item in data[:5]:
            results.append(f"Title: {item.get('title')}\nURL: {item.get('url')}")
        return "\n\n".join(results) if results else "No results found."
    except Exception as e:
        print(f"Failed to search {query}: {e}")
        return "Search failed or timed out."


from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head>
            <title>Systech API Backend</title>
            <style>
                body { font-family: sans-serif; text-align: center; padding-top: 50px; background-color: #f4f4f9; color: #333; }
                h1 { color: #8b5cf6; }
                p { font-size: 18px; }
            </style>
        </head>
        <body>
            <h1>Backend is Running! 🚀</h1>
            <p>This is the API backend for your chatbot.</p>
            <p><strong>To use the chatbot, please go to your folder and double-click <code>index.html</code>!</strong></p>
        </body>
    </html>
    """

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    if not client:
        raise HTTPException(status_code=500, detail="Azure OpenAI client not initialized properly. Check credentials.")
    
    messages_dict = [{"role": "system", "content": get_instructions()}]
    
    for msg in req.messages:
        messages_dict.append({"role": msg.role, "content": msg.content})
        
    tools = [
        {
            "type": "function",
            "function": {
                "name": "fetch_url",
                "description": "Fetches the text content of a specific URL on systechusa.com. Use this to read the careers page, services page, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The full URL to fetch, e.g. 'https://systechusa.com/careers/'"
                        }
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_website",
                "description": "Searches the systechusa.com website for a specific topic or keyword. Returns a list of relevant page titles and URLs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The keyword or topic to search for, e.g. 'Snowflake', 'CEO', 'Data Engineering'."
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]

    try:
        max_iterations = 5
        iteration = 0
        
        user_msg_lower = req.messages[-1].content.lower() if req.messages else ""
        should_use_tools = not ("customer" in user_msg_lower or "client" in user_msg_lower)
        
        while iteration < max_iterations:
            iteration += 1
            
            kwargs = {
                "model": "gpt-5.4",  # User's deployment name
                "messages": messages_dict,
                "max_completion_tokens": 1200,
                "temperature": 0.4
            }
            if should_use_tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
                
            response = client.chat.completions.create(**kwargs)
            
            response_message = response.choices[0].message
            
            if response_message.tool_calls:
                # Append the model's tool call request exactly as is
                messages_dict.append(response_message)
                
                for tool_call in response_message.tool_calls:
                    import json
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                        
                    tool_name = tool_call.function.name
                    tool_result = ""
                    
                    if tool_name == "fetch_url":
                        url = args.get("url")
                        print(f"Agent requested to browse: {url}")
                        tool_result = fetch_url_text(url)
                        if not tool_result:
                            tool_result = "Failed to fetch or page is empty."
                    
                    elif tool_name == "search_website":
                        query = args.get("query")
                        print(f"Agent requested to search site for: {query}")
                        tool_result = search_website(query)
                    
                    else:
                        tool_result = f"Unknown tool {tool_name}"
                        
                    messages_dict.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": tool_result
                    })
                # Loop continues, sending the tool outputs back to the model
            else:
                # No more tool calls, we have our final answer
                return {"response": response_message.content}
                
        # If we exit the loop due to max_iterations
        return {"response": "I'm sorry, I needed to search too many pages to find the answer and timed out. Could you please provide a more specific question?"}
            
    except Exception as e:
        print(f"Azure OpenAI Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Azure OpenAI Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
