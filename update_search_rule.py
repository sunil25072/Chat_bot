import re

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# I will update the tool instructions in the prompt
old_rule = r"1\. Use `search_website` when the user asks a specific question and you don't know the exact URL \(e\.g\., \"Do you have a Snowflake partnership\?\", \"Who is the CEO\?\"\)\. It will return a list of relevant page URLs\.\n2\. Use `fetch_url` to read the specific URL you found, or if you already know the exact URL\."

new_rule = """1. Use `search_website` when the user asks a specific question and you don't know the exact URL (e.g., "Do you have a Snowflake partnership?", "Who is the CEO?"). It will return a list of relevant page URLs.
2. Use `fetch_url` to read the specific URL you found, or if you already know the exact URL.

CRITICAL SEARCH RULE:
If the user asks about a specific webinar, blog post, or case study (e.g. "Who is the speaker in the Interview Intelligence webinar?"), DO NOT just guess the URL or check the generic `/webinars/` or `/blog/` index page. You MUST use `search_website` to find the exact specific URL for that content, and then use `fetch_url` on that exact URL to get the details!"""

text = re.sub(old_rule, new_rule, text)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('Updated search rule in app.py')
