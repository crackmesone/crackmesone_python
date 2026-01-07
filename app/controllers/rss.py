"""
RSS controller - RSS feed for crackmes.
"""

from flask import Blueprint, Response, current_app
from app.models.crackme import last_crackmes
from app.models.rating import rating_difficulty_by_crackme


def get_base_url():
    """Get configured base URL."""
    site_config = current_app.config.get('APP_CONFIG', {}).get('Site', {})
    return site_config.get('BaseURL', 'https://crackmes.one')

rss_bp = Blueprint('rss', __name__)

DIFFICULTY_NAMES = ["Very Easy", "Easy", "Medium", "Hard", "Very Hard", "Insane"]


@rss_bp.route('/rss/crackme')
def rss_crackmes():
    """Generate RSS feed for latest crackmes."""
    try:
        crackmes, _ = last_crackmes(1)
    except Exception as e:
        print(f"Error getting crackmes: {e}")
        return Response("Error generating RSS feed", status=500)

    items_xml = []
    for crackme in crackmes:
        # Calculate difficulty
        try:
            difficulties = rating_difficulty_by_crackme(crackme['hexid'])
            if difficulties:
                avg_diff = sum(d['rating'] for d in difficulties) / len(difficulties)
                diff_index = max(0, min(int(avg_diff) - 1, 5))
                diff_name = DIFFICULTY_NAMES[diff_index]
            else:
                diff_name = "Unknown"
        except Exception:
            diff_name = "Unknown"

        # Format date
        created_at = crackme.get('created_at')
        if created_at:
            pub_date = created_at.strftime('%a, %d %b %Y %H:%M:%S +0000')
        else:
            pub_date = ''

        title = f"{crackme.get('name', '')} [{crackme.get('platform', '')} - {crackme.get('lang', '')} - {diff_name}]"
        base_url = get_base_url()
        link = f"{base_url}/crackme/{crackme.get('hexid', '')}"

        item = f"""    <item>
      <title>{escape_xml(title)}</title>
      <link>{link}</link>
      <description>{escape_xml(crackme.get('info', ''))}</description>
      <author>{escape_xml(crackme.get('author', ''))}</author>
      <category>{escape_xml(crackme.get('platform', ''))}</category>
      <guid>{link}</guid>
      <pubDate>{pub_date}</pubDate>
    </item>"""
        items_xml.append(item)

    base_url = get_base_url()
    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Latest crackmes - crackmes.one</title>
    <link>{base_url}/lasts</link>
    <description>The latest 50 crackmes from crackmes.one</description>
{chr(10).join(items_xml)}
  </channel>
</rss>"""

    return Response(rss_content, mimetype='application/rss+xml; charset=utf-8')


def escape_xml(text):
    """Escape special XML characters."""
    if text is None:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))
