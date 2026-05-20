"""从 RenoDX wiki 下载 addon URLs，提取游戏名和 URL"""
import re, urllib.request

content = urllib.request.urlopen("https://raw.githubusercontent.com/wiki/clshortfuse/renodx/Mods.md").read().decode("utf-8")

games = {}  # key (normalized name) -> {name, url, addon_key}

for line in content.split('\n'):
    urls = re.findall(r'https://[^)"]+\.addon64', line)
    if not urls:
        continue
    url = urls[-1]  # Snapshot URL

    # Extract game name from table row - pattern: | GameName | Author | Badge | Badge |
    # Remove markdown links
    clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)
    cells = clean.split('|')
    if len(cells) < 3:
        continue

    # Second cell (index 1) is usually the game name
    name_cell = cells[1].strip()
    if not name_cell or len(name_cell) < 4:
        continue

    # Skip header and non-game rows
    skip = ['Game', 'Name', 'Game Name', 'Nexus Mods', 'Modder', 'Modder(s)', 'Author', 'Authors', '']
    if name_cell in skip:
        continue

    # Normalize to exe-like key
    key = name_cell.lower().replace(' ', '').replace('-', '').replace("'", '').replace('&', '').replace('_', '')
    # Extract addon name from URL
    addon_name = url.split('/')[-1]

    if key not in games:
        games[key] = {'name': name_cell, 'url': url, 'addon_name': addon_name}

print(f"Total games found: {len(games)}")
for k, v in sorted(games.items(), key=lambda x: x[1]['name']):
    print(f"  {v['name']:45s} -> {v['addon_name']}")