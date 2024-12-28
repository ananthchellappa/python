import requests
from bs4 import BeautifulSoup
from datetime import datetime
import sys

def fetch_posts(blog_url):
    posts = []
    while blog_url:  # Loop through pages
        print(f"Fetching posts from: {blog_url}")
        response = requests.get(blog_url)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch blog: {response.status_code}")
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Parse posts on the current page
        for post in soup.select(".post-outer"):
            try:
                # Extract title and link
                title_element = post.select_one(".post-title.entry-title a")
                if not title_element:
                    continue
                title = title_element.get_text(strip=True)
                link = title_element["href"]

                # Extract date
                date_element = post.find_previous("h2", class_="date-header")
                if not date_element:
                    continue
                date_str = date_element.get_text(strip=True)
                date_obj = datetime.strptime(date_str, "%A, %B %d, %Y")

                posts.append({"title": title, "link": link, "date": date_obj})
            except Exception as e:
                print(f"Error processing a post: {e}")

        # Find the "Older Posts" link
        older_posts_link = soup.select_one("a.blog-pager-older-link")
        blog_url = older_posts_link["href"] if older_posts_link else None  # Update URL for the next page
    
    return posts

def generate_html(posts):
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Blog Posts</title>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; margin: 20px; }
            h1 { color: #333; }
            ul { list-style: none; padding: 0; }
            li { margin-bottom: 10px; }
            a { text-decoration: none; color: #1a73e8; }
            a:hover { text-decoration: underline; }
            .date { color: #666; font-size: 0.9em; }
        </style>
    </head>
    <body>
        <h1>Blog Posts (Oldest First)</h1>
        <ul>
    """
    for post in posts:
        html_content += f"""
            <li>
                <a href="{post['link']}" target="_blank">{post['title']}</a>
                <div class="date">{post['date'].strftime('%B %d, %Y')}</div>
            </li>
        """
    html_content += """
        </ul>
    </body>
    </html>
    """
    with open("blog_posts.html", "w", encoding="utf-8") as file:
        file.write(html_content)
    print("HTML file generated: blog_posts.html")

def main():
    if len(sys.argv) != 2:
        print("Usage: python script.py <blog_url>")
        sys.exit(1)
    
    blog_url = sys.argv[1]
    try:
        posts = fetch_posts(blog_url)
        sorted_posts = sorted(posts, key=lambda x: x['date'])  # Sort by date
        generate_html(sorted_posts)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
