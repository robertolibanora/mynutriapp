"""Utility per generare un unico HTML SPA da dizionario pagine."""

import json
import re
from pathlib import Path


def page_id(filename: str, home_name: str = "dashboard") -> str:
    if filename == "index.html":
        return home_name
    return filename.replace(".html", "")


def extract_main_content(full_html: str, main_class: str) -> str:
    marker = f'<main class="{main_class}">'
    start = full_html.index(marker) + len(marker)
    end = full_html.index("</main>", start)
    return full_html[start:end].strip()


def extract_nav(full_html: str) -> str:
    match = re.search(r'data-nav="([^"]+)"', full_html)
    return match.group(1) if match else "home"


def extract_title(full_html: str) -> str:
    match = re.search(r"<title>([^<]+)</title>", full_html)
    if not match:
        return "App"
    return match.group(1).split("—")[0].strip()


def rewrite_links(html: str, page_files: list[str], home_name: str = "dashboard") -> str:
    for fname in page_files:
        pid = page_id(fname, home_name)
        html = html.replace(f'href="{fname}"', f'href="#" data-go="{pid}"')
        html = html.replace(f"href='{fname}'", f'href="#" data-go="{pid}"')
    html = html.replace('data-href="', 'data-go="')
    html = re.sub(r'data-redirect="([^"]+)\.html"', r'data-redirect="\1"', html)
    return html


def build_spa_html(
    *,
    pages: dict[str, str],
    css: str,
    js: str,
    fonts_link: str,
    app_title: str,
    main_class: str,
    home_id: str,
    body_class: str = "",
    extra_head: str = "",
    shell_before_main: str = "",
    shell_after_main: str = "",
    inner_main_footer: str = "",
    viewport: str = "width=device-width, initial-scale=1.0",
) -> str:
    page_files = list(pages.keys())
    sections = []
    titles = {}

    for fname, full in pages.items():
        pid = page_id(fname, home_id)
        nav = extract_nav(full)
        title = extract_title(full)
        titles[pid] = title
        content = extract_main_content(full, main_class)
        content = rewrite_links(content, page_files, home_id)
        active = " is-active" if pid == home_id else ""
        hidden = "" if pid == home_id else " hidden"
        sections.append(
            f'<section class="spa-page{active}" id="page-{pid}" data-nav="{nav}" data-title="{title}"{hidden}>\n{content}\n</section>'
        )

    spa_css = """
.spa-page { display: none; }
.spa-page.is-active { display: block; }
"""
    titles_json = json.dumps(titles, ensure_ascii=False)

    spa_boot = f"""
document.addEventListener('DOMContentLoaded', function() {{
  var PAGE_TITLES = {titles_json};
  var HOME = '{home_id}';

  function goTo(pageId) {{
    if (!document.getElementById('page-' + pageId)) pageId = HOME;
    document.querySelectorAll('.spa-page').forEach(function(p) {{
      p.classList.remove('is-active');
      p.hidden = true;
    }});
    var page = document.getElementById('page-' + pageId);
    page.hidden = false;
    page.classList.add('is-active');
    document.body.setAttribute('data-nav', page.getAttribute('data-nav') || HOME);
    document.title = (PAGE_TITLES[pageId] || '{app_title}') + ' — {app_title}';
    window.scrollTo(0, 0);
    if (location.hash.replace('#', '') !== pageId) location.hash = pageId;
    if (typeof window.__spaAfterNav === 'function') window.__spaAfterNav(pageId);
  }}

  document.addEventListener('click', function(e) {{
    var go = e.target.closest('[data-go]');
    if (go) {{ e.preventDefault(); goTo(go.getAttribute('data-go')); return; }}
  }});

  window.goTo = goTo;
  var initial = location.hash.replace('#', '') || HOME;
  goTo(initial);
  window.addEventListener('hashchange', function() {{
    goTo(location.hash.replace('#', '') || HOME);
  }});
}});
"""

    body_attr = f' class="{body_class}"' if body_class else ""
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="{viewport}">
  <title>{app_title}</title>
  {fonts_link}
  {extra_head}
  <style>
{css}
{spa_css}
  </style>
</head>
<body{body_attr} data-nav="{home_id}">
{shell_before_main}
  <main class="{main_class}">
{chr(10).join(sections)}
{inner_main_footer}
  </main>
{shell_after_main}
  <script>
{js}
{spa_boot}
  </script>
</body>
</html>"""
