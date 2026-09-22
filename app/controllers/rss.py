"""RSS controller for the site's latest activity."""

from datetime import datetime, timezone

from flask import Blueprint, Response, current_app

from app.models.crackme import crackmes_by_hexids, last_crackmes
from app.models.rating import rating_difficulty_by_crackme
from app.models.solution import latest_solutions
from app.models.solve import latest_solves
from app.models.user import users_by_hexids


def get_base_url():
    """Get configured base URL."""
    site_config = current_app.config.get('APP_CONFIG', {}).get('Site', {})
    return site_config.get('BaseURL', 'https://crackmes.one')


rss_bp = Blueprint('rss', __name__)

DIFFICULTY_NAMES = ["Very Easy", "Easy", "Medium", "Hard", "Very Hard", "Insane"]


def _pub_date(item):
    created_at = item.get('created_at')
    if not created_at:
        return ''
    return created_at.strftime('%a, %d %b %Y %H:%M:%S +0000')


def _crackme_activity(crackme):
    try:
        difficulties = rating_difficulty_by_crackme(crackme['hexid'])
        if difficulties:
            average = sum(row['rating'] for row in difficulties) / len(difficulties)
            difficulty = DIFFICULTY_NAMES[max(0, min(int(average) - 1, 5))]
        else:
            difficulty = "Unknown"
    except Exception:
        difficulty = "Unknown"

    return {
        'created_at': crackme.get('created_at'),
        'title': (f"New crackme: {crackme.get('name', '')} "
                  f"[{crackme.get('platform', '')} - {crackme.get('lang', '')} - {difficulty}]"),
        'path': f"/crackme/{crackme.get('hexid', '')}",
        'description': crackme.get('info', ''),
        'author': crackme.get('author', ''),
        'category': 'Crackme',
        'guid_suffix': '',
    }


def _solution_activity(solution):
    return {
        'created_at': solution.get('created_at'),
        'title': f"New solution for {solution.get('crackmename', '')}",
        'path': f"/solution/{solution.get('hexid', '')}",
        'description': solution.get('info', ''),
        'author': solution.get('author', ''),
        'category': 'Solution',
        'guid_suffix': '',
    }


def _solve_activities(solves):
    users = users_by_hexids(solve['user_hexid'] for solve in solves)
    crackmes = crackmes_by_hexids(solve['crackme_hexid'] for solve in solves)
    activities = []
    for solve in solves:
        username = users.get(solve['user_hexid'], {}).get('name', 'Deleted user')
        crackme_name = crackmes.get(solve['crackme_hexid'], {}).get(
            'name', 'Unknown crackme'
        )
        activities.append({
            'created_at': solve.get('created_at'),
            'title': f"New solve: {username} solved {crackme_name}",
            'path': f"/crackme/{solve['crackme_hexid']}",
            'description': f"Awarded {solve.get('points', 0)} points.",
            'author': username,
            'category': 'Solve',
            'guid_suffix': f"#solve-{solve.get('hexid', solve.get('_id', ''))}",
        })
    return activities


@rss_bp.route('/rss')
@rss_bp.route('/rss/crackme')
def rss_activity():
    """Generate one chronological feed for crackmes, solutions, and solves."""
    try:
        crackmes, _ = last_crackmes(1)
        solutions, _ = latest_solutions(1)
        solves, _ = latest_solves(1)
        activities = [_crackme_activity(crackme) for crackme in crackmes]
        activities.extend(_solution_activity(solution) for solution in solutions)
        activities.extend(_solve_activities(solves))
        oldest = datetime.min.replace(tzinfo=timezone.utc)
        activities.sort(key=lambda item: item.get('created_at') or oldest, reverse=True)
        activities = activities[:50]
    except Exception as error:
        print(f"Error getting latest activity: {error}")
        return Response("Error generating RSS feed", status=500)

    base_url = get_base_url()
    items_xml = []
    for activity in activities:
        link = f"{base_url}{activity['path']}"
        guid = f"{link}{activity['guid_suffix']}"
        items_xml.append(f"""    <item>
      <title>{escape_xml(activity['title'])}</title>
      <link>{escape_xml(link)}</link>
      <description>{escape_xml(activity['description'])}</description>
      <author>{escape_xml(activity['author'])}</author>
      <category>{activity['category']}</category>
      <guid>{escape_xml(guid)}</guid>
      <pubDate>{_pub_date(activity)}</pubDate>
    </item>""")

    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Latest activity - crackmes.one</title>
    <link>{escape_xml(base_url)}/latest</link>
    <description>The latest crackmes, solutions, and solves from crackmes.one</description>
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
