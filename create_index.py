import os
from datetime import datetime

HTML_DIR = "html"  # your directory
OUTPUT_FILE = os.path.join(HTML_DIR, "index.html")


def ordinal(n):
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]}"


def format_datetime(dt):
    day_name = dt.strftime("%A")
    month = dt.strftime("%B")
    day = ordinal(dt.day)
    time = dt.strftime("%I:%M %p").lstrip("0").lower()
    return f"{day_name} {month} {day}, {time}"


files = []

for filename in os.listdir(HTML_DIR):
    if filename.startswith("output_") and filename.endswith(".html"):
        try:
            timestamp_str = filename.replace("output_", "").replace(".html", "")
            dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            files.append((dt, filename))
        except ValueError:
            continue  # skip malformed files

# Sort chronologically (oldest first)
files.sort(key=lambda x: x[0])

# Build HTML
html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>HTML Index</title>
</head>
<body>
    <h1>HTML Files</h1>
    <ul>
"""

for dt, filename in files:
    display_date = format_datetime(dt)
    html_content += f'        <li><a href="{filename}">{display_date}</a></li>\n'

html_content += """    </ul>
</body>
</html>
"""

# Write index.html
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"Index file created at {OUTPUT_FILE}")

