#!/usr/bin/env python3
"""
2026 World Cup Data Scraper
- Match results: FIFA.com
- Prediction odds: Polymarket CLOB API
Writes to data.json in the parent directory.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    # Fallback for GitHub Actions where requests might not be installed
    import urllib.request
    import urllib.error

    class RequestsCompat:
        @staticmethod
        def get(url, timeout=15, headers=None):
            req = urllib.request.Request(url)
            if headers:
                for k, v in headers.items():
                    req.add_header(k, v)
            try:
                resp = urllib.request.urlopen(req, timeout=timeout)
                return type('Resp', (), {
                    'status_code': resp.getcode(),
                    'ok': 200 <= resp.getcode() < 300,
                    'json': lambda: json.loads(resp.read().decode('utf-8')),
                    'text': resp.read().decode('utf-8'),
                })()
            except urllib.error.HTTPError as e:
                return type('Resp', (), {
                    'status_code': e.code,
                    'ok': False,
                    'json': lambda: None,
                    'text': '',
                })()
            except urllib.error.URLError:
                return type('Resp', (), {
                    'status_code': 0, 'ok': False,
                    'json': lambda: None, 'text': '',
                })()

    requests = RequestsCompat()

# --- Config ---
DATA_DIR = Path(__file__).parent.parent
DATA_FILE = DATA_DIR / 'data.json'
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) WC2026-Scraper/1.0'

# FIFA data sources
FIFA_MATCH_CENTER = 'https://www.fifa.com/en/tournaments/mens/mensworldcup/2026/match-center'

# Polymarket CLOB API
POLYMARKET_API = 'https://clob.polymarket.com'
POLYMARKET_SEARCH = f'{POLYMARKET_API}/markets'
POLYMARKET_PRICE = f'{POLYMARKET_API}/price'

def load_current_data():
    """Load existing data.json or create empty structure."""
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'matches': [], 'predictions': {}}


def save_data(data):
    """Write updated data back to data.json."""
    data['lastUpdated'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S') + '+08:00'
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'  Saved {DATA_FILE}')


def scrape_fifa_matches(data):
    """Try to fetch match results from FIFA.com."""
    print('  [FIFA] Fetching match center...')
    
    try:
        resp = requests.get(FIFA_MATCH_CENTER, timeout=20, headers={
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/json,*/*',
        })
        
        if not resp.ok:
            print(f'  [FIFA] HTTP {resp.status_code}, skipping')
            return False
        
        html = resp.text if hasattr(resp, 'text') else ''
        
        # Try to find embedded JSON data in FIFA pages
        # FIFA match center often has JSON-LD or embedded match data
        import re
        
        # Look for match data patterns in FIFA HTML
        matches_updated = 0
        
        # Try 1: JSON-LD structured data
        jsonld_pattern = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)
        for match_ld in jsonld_pattern.findall(html):
            try:
                ld_data = json.loads(match_ld)
                if isinstance(ld_data, dict) and 'match' in str(ld_data).lower():
                    # Extract scores from JSON-LD
                    pass
            except json.JSONDecodeError:
                pass
        
        # Try 2: FIFA's __NEXT_DATA__ or window.__INITIAL_STATE__
        state_pattern = re.compile(r'__NEXT_DATA__\s*=\s*({.*?});', re.DOTALL)
        state_match = state_pattern.search(html)
        if state_match:
            try:
                state = json.loads(state_match.group(1))
                # Navigate state to find match data...
                # Structure varies by FIFA page version
                pass
            except (json.JSONDecodeError, KeyError):
                pass
        
        # Try 3: Open Graph / meta data approach
        # Simple: look for score patterns like "2-1" near team names
        # This is a very basic fallback
        
        print(f'  [FIFA] Page fetched but custom parser needed. {matches_updated} matches updated.')
        return matches_updated > 0
        
    except Exception as e:
        print(f'  [FIFA] Error: {e}')
        return False


def fetch_polymarket_prices():
    """Fetch all 2026 World Cup prediction markets from Polymarket."""
    print('  [Polymarket] Searching for markets...')
    
    try:
        # Search for World Cup 2026 markets
        resp = requests.get(POLYMARKET_SEARCH, timeout=20, params={
            'tag': 'world-cup-2026',
            'limit': 200,
            'closed': 'false',
        }, headers={'User-Agent': USER_AGENT})
        
        if not resp.ok:
            # Try alternative search
            resp = requests.get(POLYMARKET_SEARCH, timeout=20, params={
                'search': 'world cup 2026',
                'limit': 200,
            }, headers={'User-Agent': USER_AGENT})
        
        if not resp.ok:
            print(f'  [Polymarket] HTTP {resp.status_code}, skipping')
            return None
        
        markets = resp.json()
        if isinstance(markets, dict):
            markets = markets.get('data', markets.get('markets', []))
        if not isinstance(markets, list):
            markets = [markets]
        
        print(f'  [Polymarket] Found {len(markets)} markets')
        
        predictions = {}
        
        for market in markets:
            try:
                # Parse market info
                question = str(market.get('question', '') or '')
                outcomes = market.get('outcomes', [])
                prices = market.get('prices', [])
                
                # Only interested in match outcome markets
                if not any(kw in question.lower() for kw in [' vs ', ' vs ', 'winner', 'match']):
                    continue
                
                # Get prices
                if not prices and 'outcomePrices' in market:
                    prices_str = market['outcomePrices']
                    if isinstance(prices_str, str):
                        prices = json.loads(prices_str) if prices_str.startswith('[') else []
                    else:
                        prices = prices_str if isinstance(prices_str, list) else []
                
                # Map outcomes to prices
                outcome_prices = {}
                for i, outcome in enumerate(outcomes):
                    outcome_prices[str(outcome).lower()] = float(prices[i]) if i < len(prices) else 0.5
                
                # Generate the match key (FIFA code pair)
                # e.g., "Mexico vs South Africa" -> "MEX_RSA"
                # This mapping needs to be customized based on the market question
                
                # Store raw data for later matching
                predictions[question] = {
                    'home': outcome_prices.get('yes', outcome_prices.get('home', None)),
                    'draw': outcome_prices.get('draw', None),
                    'away': outcome_prices.get('no', outcome_prices.get('away', None)),
                    'raw_question': question,
                }
                
            except (KeyError, ValueError, TypeError) as e:
                continue
        
        return predictions
        
    except Exception as e:
        print(f'  [Polymarket] Error: {e}')
        return None


def merge_predictions(data, poly_data):
    """Merge Polymarket predictions into data, matching by team names."""
    if not poly_data:
        return
    
    # Build team name to FIFA code mapping
    team_to_code = {}
    for match in data.get('matches', []):
        if 'home' in match and 'cc' in match['home']:
            team_to_code[match['home']['name'].lower()] = match['home']['cc']
        if 'away' in match and 'cc' in match['away']:
            team_to_code[match['away']['name'].lower()] = match['away']['cc']
    
    matched = 0
    for raw_question, pred_data in poly_data.items():
        q = raw_question.lower()
        
        # Try to parse "TeamA vs TeamB" format
        for sep in [' vs ', ' vs ']:
            if sep in q:
                parts = q.split(sep)
                if len(parts) >= 2:
                    # Remove parenthetical notes
                    team_a = parts[0].split('(')[0].strip()
                    team_b = parts[1].split('(')[0].strip()
                    
                    # Try to find matching FIFA codes
                    cc_a = team_to_code.get(team_a)
                    cc_b = team_to_code.get(team_b)
                    
                    if cc_a and cc_b:
                        key = f'{cc_a}_{cc_b}'
                        if pred_data.get('home') is not None and pred_data.get('draw') is not None:
                            data['predictions'][key] = {
                                'home': pred_data['home'],
                                'draw': pred_data['draw'],
                            }
                            matched += 1
    
    print(f'  [Polymarket] Matched {matched} predictions')


def scrape_polymarket(data):
    """Fetch and merge Polymarket data."""
    print('  [Polymarket] Fetching prices...')
    poly_data = fetch_polymarket_prices()
    if poly_data:
        merge_predictions(data, poly_data)
        return True
    return False


def main():
    print('=== 2026 World Cup Data Scraper ===')
    print(f'Time: {datetime.now(timezone.utc).isoformat()}')
    
    data = load_current_data()
    print(f'Loaded {len(data.get("matches", []))} matches, {len(data.get("predictions", {}))} predictions')
    
    # Step 1: Scrape FIFA match results
    print('\n[1/2] FIFA Match Results:')
    scrape_fifa_matches(data)
    
    # Step 2: Scrape Polymarket predictions
    print('\n[2/2] Polymarket Predictions:')
    scrape_polymarket(data)
    
    # Save
    print('\nSaving...')
    save_data(data)
    print('Done.')


if __name__ == '__main__':
    main()
