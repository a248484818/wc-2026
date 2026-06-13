#!/usr/bin/env python3
"""
2026 World Cup Data Scraper
Uses Playwright to fetch real data from Polymarket and FIFA.com.
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent
DATA_FILE = DATA_DIR / 'data.json'
NAV_TIMEOUT = 30000

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'matches': [], 'predictions': {}}


def save_data(data):
    data['lastUpdated'] = datetime.now(timezone.utc).strftime(
        '%Y-%m-%d %H:%M:%S') + '+08:00'
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'  Saved {DATA_FILE}')


def team_code_reverse(predictions):
    """Build a reverse map from team name to FIFA code."""
    name_to_code = {}
    for key in predictions:
        if '_' in key and not key.endswith('_SP') and not key.endswith('_OU') \
                and not key.endswith('_SPREADS') and not key.endswith('_OUS'):
            parts = key.split('_')
            if len(parts) == 2:
                # We need actual team names; this is approximate
                pass
    return name_to_code


# ---------- Polymarket Scraper ----------

def scrape_polymarket(data):
    """Scrape all match odds from Polymarket using Playwright."""
    if not HAS_PLAYWRIGHT:
        print('  [Polymarket] Playwright not installed, skipping')
        return

    print('  [Polymarket] Launching browser...')
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            page.goto(
                'https://polymarket.com/zh/sports/world-cup/games',
                timeout=NAV_TIMEOUT,
                wait_until='networkidle'
            )
            time.sleep(3)

            # Scroll to load all matches (virtual scroller)
            prev_height = -1
            scroll_attempts = 0
            while scroll_attempts < 30:
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                time.sleep(1.5)
                new_height = page.evaluate('document.body.scrollHeight')
                if new_height == prev_height:
                    scroll_attempts += 1
                else:
                    scroll_attempts = 0
                prev_height = new_height

            # Get all visible text from the page
            body_text = page.evaluate(
                '() => document.body.innerText')

            # Parse match data from text
            lines = body_text.split('\n')
            i = 0
            matches_parsed = 0
            while i < len(lines):
                line = lines[i].strip()
                # Look for time markers (start of a match block)
                time_match = re.match(r'^[上下]午 \d+:\d+$', line)
                if not time_match:
                    i += 1
                    continue

                # Found a time - next lines should have team data
                time_val = line
                home_team = ''
                away_team = ''
                ml_home = ml_draw = ml_away = None
                sp_home_team = sp_home_line = sp_home_price = None
                sp_away_team = sp_away_line = sp_away_price = None
                ou_over = ou_under = None

                j = i + 1
                while j < min(i + 30, len(lines)):
                    l2 = lines[j].strip()
                    if not l2:
                        j += 1
                        continue

                    # Moneyline: "QAT5.9¢"
                    ml_m = re.match(r'^([A-Z]{3})([\d.]+)¢$', l2)
                    if ml_m and ml_m.group(1) != 'DRA':
                        if not home_team:
                            home_team = ml_m.group(1)
                            ml_home = float(ml_m.group(2)) / 100
                        else:
                            away_team = ml_m.group(1)
                            ml_away = float(ml_m.group(2)) / 100
                        j += 1
                        continue

                    dr_m = re.match(r'^DRAW([\d.]+)¢$', l2)
                    if dr_m:
                        ml_draw = float(dr_m.group(1)) / 100
                        j += 1
                        continue

                    # Spread: "qat +1.5 4 0 ¢"
                    sp_m = re.match(
                        r'^([a-z]{3}) ([+-][\d.]+) (\d+) (\d+) ¢$', l2)
                    if sp_m:
                        side = sp_m.group(1).upper()
                        sp_line = sp_m.group(2)
                        sp_price = (int(sp_m.group(3)) * 10 +
                                    int(sp_m.group(4))) / 100
                        if side == home_team:
                            sp_home_team = side
                            sp_home_line = sp_line
                            sp_home_price = sp_price
                        else:
                            sp_away_team = side
                            sp_away_line = sp_line
                            sp_away_price = sp_price
                        j += 1
                        continue

                    # Total: "O 2.5 6 2 ¢" or "U 2.5 3 9 ¢"
                    ou_m = re.match(
                        r'^([OU]) ([\d.]+) (\d+) (\d+) ¢$', l2)
                    if ou_m:
                        total = ou_m.group(2)
                        price = (int(ou_m.group(3)) * 10 +
                                 int(ou_m.group(4))) / 100
                        if ou_m.group(1) == 'O':
                            ou_over = {'total': total, 'price': price}
                        else:
                            ou_under = {'total': total, 'price': price}
                        j += 1
                        continue

                    # End of match block - next time or empty line
                    if re.match(r'^[上下]午 \d+:\d+$', l2) or \
                            re.match(r'^[A-Z][a-z]+,', l2):
                        break
                    j += 1

                # Save match if we have all required data
                if home_team and away_team and ml_home is not None and \
                        ml_draw is not None and ml_away is not None:
                    key = f'{home_team}_{away_team}'
                    data['predictions'][key] = {
                        'home': ml_home, 'draw': ml_draw}

                    if sp_home_price is not None:
                        data['predictions'][f'{key}_SP'] = {
                            'home': sp_home_price, 'draw': None}
                        data['predictions'][f'{key}_SPREADS'] = {
                            sp_home_line: sp_home_price}

                    if ou_over is not None:
                        data['predictions'][f'{key}_OU'] = {
                            'home': ou_over['price'], 'draw': None}
                        data['predictions'][f'{key}_OUS'] = {
                            ou_over['total']: ou_over['price']}

                    matches_parsed += 1

                i = j if j > i + 1 else i + 1

            browser.close()
            print(f'  [Polymarket] Parsed {matches_parsed} matches')

    except Exception as e:
        print(f'  [Polymarket] Error: {e}')


# ---------- FIFA Scraper ----------

def scrape_fifa(data):
    """Scrape match results from FIFA.com."""
    if not HAS_PLAYWRIGHT:
        print('  [FIFA] Playwright not installed, skipping')
        return

    print('  [FIFA] Fetching match center...')
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            page.goto(
                'https://www.fifa.com/en/tournaments/mens/'
                'mensworldcup/2026/match-center',
                timeout=NAV_TIMEOUT,
                wait_until='networkidle'
            )
            time.sleep(3)

            # Scroll to load all matches
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(2)

            body_text = page.evaluate(
                '() => document.body.innerText')

            # Parse scores from page text
            lines = body_text.split('\n')
            matches_updated = 0
            for line in lines:
                # Look for score patterns like "2-1" or "3-0"
                score_m = re.search(
                    r'([A-Za-z\s]+)\s+(\d+)[-–](\d+)\s+([A-Za-z\s]+)', line)
                if score_m:
                    team1 = score_m.group(1).strip().upper()[:3]
                    team2 = score_m.group(4).strip().upper()[:3]
                    score1 = int(score_m.group(2))
                    score2 = int(score_m.group(3))

                    # Try to match to our matches
                    for match in data.get('matches', []):
                        h = match.get('home', {}).get('cc', '')
                        a = match.get('away', {}).get('cc', '')
                        if (h == team1 and a == team2) or \
                                (h == team2 and a == team1):
                            match['status'] = 'FINISHED'
                            if h == team1:
                                match['home']['score'] = score1
                                match['away']['score'] = score2
                            else:
                                match['home']['score'] = score2
                                match['away']['score'] = score1
                            matches_updated += 1
                            break

            browser.close()
            print(f'  [FIFA] Updated {matches_updated} matches')

    except Exception as e:
        print(f'  [FIFA] Error: {e}')


# ---------- Main ----------

def main():
    print('=== 2026 World Cup Data Scraper ===')
    print(f'Time: {datetime.now(timezone.utc).isoformat()}')

    data = load_data()
    print(f'Loaded {len(data.get("matches", []))} matches, '
          f'{len(data.get("predictions", {}))} predictions')

    print('\n[1/2] FIFA Match Results:')
    scrape_fifa(data)

    print('\n[2/2] Polymarket Predictions:')
    scrape_polymarket(data)

    print('\nSaving...')
    save_data(data)
    print('Done.')


if __name__ == '__main__':
    main()
