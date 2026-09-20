# Complete, well-commented, runnable code for this single file
import requests
import json
import time
import re
import os
import sys

CONFIG = {
    'base_domain': 'https://themoviebox.xyz',
    'jwt_token': '', # Auto-fetched via script
    
    'output_file': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'a_dab.json'),
    'start_page': 1,
    'per_page': 28,       
    'delay_ms': 800,      
    
    'cooldown_every_pages': 10,
    'cooldown_seconds': 8, 
    
    'filter': {
        'tabId': 2,
        'classify': 'Hindi dub',
        'country': 'All',
        'genre': 'Animation',
        'sort': 'ForYou', 
        'year': 'All'
    }
}

# Auto-generated API endpoints
CONFIG['api_url'] = f"{CONFIG['base_domain']}/wefeed-h5api-bff/subject/filter"
CONFIG['play_api'] = f"{CONFIG['base_domain']}/wefeed-h5api-bff/subject/play"

# We use a global requests session to persist cookies naturally (like real browsers)
session = requests.Session()

def get_stealth_headers(token="", base_domain=""):
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9,bn;q=0.8',
        'Origin': base_domain,
        'Referer': f"{base_domain}/",
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }
    if token:
        headers['Authorization'] = f"Bearer {token}"
    return headers

def fetch_initial_token_and_cookie():
    # সরাসরি মুভি ফিল্টার পেজে হিট করলে টোকেন পাওয়ার সম্ভাবনা ১০০%
    url = f"{CONFIG['base_domain']}/web/film?type=/home/movieFilter"
    headers = get_stealth_headers(base_domain=CONFIG['base_domain'])
    
    try:
        response = session.get(url, headers=headers, timeout=15, verify=False)
        token = ""
        
        # Check cookies first
        token = session.cookies.get('mb_auth_token') or session.cookies.get('mb_token')
        
        # Fallback to NEXT_DATA extraction
        if not token:
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', response.text, re.DOTALL)
            if match:
                token_match = re.search(r'"token"\s*:\s*"([a-zA-Z0-9\.\-_]+)"', match.group(1), re.IGNORECASE)
                if token_match:
                    token = token_match.group(1)
        return token
    except Exception as e:
        print(f"Error fetching initial token: {e}")
        return ""

def request_scroll_api(url, payload, token, base_domain):
    headers = get_stealth_headers(token, base_domain)
    headers['Content-Type'] = 'application/json'
    
    try:
        response = session.post(url, json=payload, headers=headers, timeout=20, verify=False)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error requesting list API: {e}")
    return None

def fetch_movie_stream_exact(movie_id, title, se, ep, fallback_token, detail_path):
    if not detail_path:
        # Generate slug if empty
        detail_path = re.sub(r'[^A-Za-z0-9-]+', '-', title).strip('-').lower()
        if not detail_path: detail_path = "detail"

    target_url = f"{CONFIG['base_domain']}/movies/{detail_path}?id={movie_id}&type=/movie/detail&detailSe={se}&detailEp={ep}&lang=en"

    browser_headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'priority': 'u=0, i',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    }

    full_detail_data = {}
    page_description = ""

    # Visit detail page to extract NEXT_DATA and simulate real user flow
    try:
        html_response = session.get(target_url, headers=browser_headers, timeout=15, verify=False)
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_response.text, re.DOTALL)
        if match:
            next_data = json.loads(match.group(1))
            full_detail_data = next_data.get('props', {}).get('pageProps', {}).get('detail', {})
            page_description = full_detail_data.get('description', full_detail_data.get('brief', ''))
    except Exception:
        pass

    token = session.cookies.get('mb_auth_token') or session.cookies.get('mb_token') or fallback_token

    play_api_url = f"{CONFIG['play_api']}?subjectId={movie_id}&se={se}&ep={ep}&detailPath={detail_path}&streamSignType=1&supportCodecs%5Bh264%5D=1"
    
    api_headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9',
        'origin': CONFIG['base_domain'],
        'referer': target_url, 
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    }
    if token:
        api_headers['authorization'] = f"Bearer {token}"

    try:
        play_response = session.get(play_api_url, headers=api_headers, timeout=15, verify=False)
        if play_response.status_code != 200: return None
        
        data = play_response.json()
        if 'data' not in data: return None

        final_url = None
        quality = None
        stream_type = 'm3u8'
        sign_cookie = ''

        # Priority MP4
        if data['data'].get('streams'):
            mp4_list = {int(st.get('resolutions', 0)): st for st in data['data']['streams'] if st.get('url')}
            if mp4_list:
                best_res = sorted(mp4_list.keys(), reverse=True)[0]
                best_mp4 = mp4_list[best_res]
                quality = f"{best_res}P"
                final_url = best_mp4['url']
                stream_type = 'mp4'
                sign_cookie = best_mp4.get('signCookie', '')
        
        # Fallback DASH
        elif data['data'].get('dash') and data['data']['dash'][0].get('url'):
            quality = 'DASH'
            final_url = data['data']['dash'][0]['url']
            stream_type = 'dash'
            sign_cookie = data['data']['dash'][0].get('signCookie', '')

        if not final_url: return None

        return {
            'url': final_url,
            'quality': quality or 'HD',
            'streamType': stream_type,
            'signCookie': sign_cookie,
            'pageDescription': page_description,
            'fullDetailData': full_detail_data
        }
    except Exception:
        return None

def extract_trailer_url(trailer_data):
    if not trailer_data: return ""
    if isinstance(trailer_data, str) and trailer_data.startswith('http'): return trailer_data
    
    if isinstance(trailer_data, dict):
        if trailer_data.get('videoAddress', {}).get('url'):
            return trailer_data['videoAddress']['url']
        if trailer_data.get('url'): return trailer_data['url']
        if trailer_data.get('videoUrl'): return trailer_data['videoUrl']
    return ""

def format_to_desired_json(movie, stream_info, config):
    movie_data = movie.copy()
    if stream_info and stream_info.get('fullDetailData'):
        movie_data.update(stream_info['fullDetailData'])

    release_date = str(movie_data.get('releaseDate') or movie_data.get('year') or '')
    year_match = re.search(r'(\d{4})', release_date)
    year = year_match.group(1) if year_match else ''

    raw_title = str(movie_data.get('title') or movie_data.get('name') or 'Unknown')
    # Remove any bracketed words like [Bengali]
    clean_title = re.sub(r'\[.*?\]', '', raw_title).strip()
    clean_title = re.sub(r'\s+', ' ', clean_title)
    
    title_with_year = f"{clean_title} ({year})" if year and f"({year})" not in clean_title else clean_title

    raw_genres = movie_data.get('genre') or movie_data.get('genres') or movie_data.get('categories') or ["Unknown"]
    if isinstance(raw_genres, str): raw_genres = raw_genres.split(',')
    genres = [g.strip() for g in raw_genres if g.strip()] or ["Unknown"]

    director = 'Unknown'
    staff_list = movie_data.get('staffList', [])
    if isinstance(staff_list, list) and staff_list:
        directors = [s['name'] for s in staff_list if str(s.get('staffType')) == '2' and s.get('name')]
        director = ', '.join(directors) if directors else staff_list[0].get('name', 'Unknown')

    trailer_url = extract_trailer_url(movie_data.get('trailer') or movie_data.get('trailerUrl'))

    storyline = stream_info.get('pageDescription', '') if stream_info else ''
    if not storyline: storyline = movie_data.get('description', '')
    if not storyline: storyline = 'No storyline available.'

    cover_data = movie_data.get('cover', '')
    poster_url = cover_data.get('url', '') if isinstance(cover_data, dict) else (cover_data if isinstance(cover_data, str) else '')

    return {
        "id": str(movie_data.get('subjectId') or movie_data.get('id') or ''),
        "title": title_with_year,
        "director": director,
        "releaseDate": release_date,
        "category": config['filter'].get('classify', 'Unknown'),
        "genre": genres,
        "language": str(movie_data.get('language') or movie_data.get('corner') or 'Unknown'),
        "imdbRating": str(movie_data.get('imdbRatingValue') or movie_data.get('score') or movie_data.get('rating') or '0.0'),
        "imdbVotes": int(movie_data.get('imdbRatingCount') or movie_data.get('votes') or 0),
        "storyline": storyline.strip(),
        "posterUrl": poster_url,
        "sliderUrl": poster_url,
        "sliderStatus": "on",
        "streamUrl": str(stream_info.get('url', '') if stream_info else ''),
        "downUrl": str(stream_info.get('url', '') if stream_info else ''),
        "downStatus": "on",
        "status": "active",
        "premium": bool(movie_data.get('isVip')),
        "triler": trailer_url,
        "quality": "HD",
        "resolution": str(stream_info.get('quality', 'HD') if stream_info else 'HD'),
        "streamType": str(stream_info.get('streamType', 'm3u8') if stream_info else 'm3u8'),
        "headers": {
            "referer": f"{config['base_domain']}/",
            "origin": config['base_domain'],
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "cookie": str(stream_info.get('signCookie', '') if stream_info else ''),
            "sec-ch-ua-platform": "Windows",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site"
        }
    }

if __name__ == "__main__":
    # Disable warnings for unverified HTTPS requests
    requests.packages.urllib3.disable_warnings()
    
    print("====================================================")
    print("    MovieBox Auto Scraper (Python Edition)")
    print("====================================================")

    auto_token = fetch_initial_token_and_cookie()
    if auto_token:
        CONFIG['jwt_token'] = auto_token
        print("✅ [SUCCESS] Automatically fetched latest JWT token!", flush=True)
    else:
        print("⚠️ [WARNING] Failed to fetch auto token!", flush=True)

    all_movies = []
    movies_map = {}
    seen_in_this_run = set()

    # Load existing to avoid skipping, but to refresh links
    if os.path.exists(CONFIG['output_file']):
        try:
            with open(CONFIG['output_file'], 'r', encoding='utf-8') as f:
                existing = json.load(f)
                if isinstance(existing, list):
                    all_movies = existing
                    for idx, m in enumerate(all_movies):
                        if m.get('id'):
                            movies_map[str(m['id'])] = idx
            print(f"[INFO] Found {len(all_movies)} existing movies. Links will be refreshed.", flush=True)
        except Exception as e:
            print(f"[WARNING] Could not read existing JSON: {e}")

    page = CONFIG['start_page']
    pages_scraped_in_batch = 0

    while True:
        print(f"\n[PAGE {page}] Fetching data... ", flush=True)
        
        payload = {
            'channelId': 1, # Added channelId as requested by API
            'tabId': CONFIG['filter']['tabId'],
            'classify': CONFIG['filter']['classify'],
            'country': CONFIG['filter']['country'],
            'genre': CONFIG['filter']['genre'],
            'sort': CONFIG['filter']['sort'],
            'year': CONFIG['filter']['year'],
            'page': page,
            'perPage': CONFIG['per_page']
        }

        response = request_scroll_api(CONFIG['api_url'], payload, CONFIG['jwt_token'], CONFIG['base_domain'])

        if not response:
            print("[STOP] API Connection issue.", flush=True)
            break

        # Safe extraction of items to avoid 'str' object has no attribute 'get'
        raw_data = response.get('data', {})
        items = []
        if isinstance(raw_data, dict):
            items = raw_data.get('list') or raw_data.get('items') or raw_data.get('subjects') or []
        elif isinstance(raw_data, list):
            items = raw_data
            
        if not isinstance(items, list):
            items = []

        count = len(items)
        print(f" -> Found: {count} items.", flush=True)

        if count == 0:
            print("🎉 [FINISHED] No more new movies available!", flush=True)
            break

        processed_this_page = 0

        for movie in items:
            if not isinstance(movie, dict):
                continue # Skip if the item is not a dictionary
                
            mid = str(movie.get('subjectId') or movie.get('id') or '')
            title = movie.get('title') or movie.get('name') or 'Unknown'
            detail_path = movie.get('detailPath', '')

            if not mid: continue
            
            type_val = str(movie.get('subjectType', 1))
            ep_count = int(movie.get('episodeCount') or movie.get('curEpisode') or movie.get('totalEpisodes') or 1)

            # Filtering out Multi-Episode Series but allowing single episodes
            if type_val == '2':
                if ep_count > 1:
                    print(f"   ⏭ {title} [Skipping Multi-Episode Series]", flush=True)
                    continue
                else:
                    print(f"   ▶ {title} [Single-Episode Series -> Fetching]", flush=True)

            if mid in seen_in_this_run:
                continue
            
            seen_in_this_run.add(mid)
            processed_this_page += 1

            # Dynamic Season/Episode mapping based on original API data
            se = int(movie.get('season', 0))
            if se <= 0: se = 1 if type_val == '2' else 0
            ep = int(movie.get('curEpisode', 0))
            if ep <= 0: ep = 1 if type_val == '2' else 0

            is_existing = str(mid) in movies_map

            if is_existing:
                print(f"   ⟳ {title} [Refreshing]... ", end="", flush=True)
            else:
                print(f"   * {title} [Fetching]... ", end="", flush=True)

            stream_info = fetch_movie_stream_exact(mid, title, se, ep, CONFIG['jwt_token'], detail_path)

            # Strict skip if no link
            if not stream_info or not stream_info.get('url'):
                print("[No Link - Skipped]", flush=True)
                continue

            if is_existing:
                idx = movies_map[str(mid)]
                all_movies[idx]['streamUrl'] = stream_info['url']
                all_movies[idx]['downUrl'] = stream_info['url']
                all_movies[idx]['resolution'] = stream_info.get('quality', 'HD')
                all_movies[idx]['streamType'] = stream_info.get('streamType', 'm3u8')
                
                # Refresh Cookie in headers safely
                if 'headers' not in all_movies[idx]: all_movies[idx]['headers'] = {}
                all_movies[idx]['headers']['cookie'] = stream_info.get('signCookie', '')
                
                # Update Storyline if it was missing
                if not all_movies[idx].get('storyline') or all_movies[idx]['storyline'] == 'No storyline available.':
                    if stream_info.get('pageDescription'): 
                        all_movies[idx]['storyline'] = stream_info['pageDescription']
                print("[Success - Refreshed]", flush=True)
            else:
                formatted = format_to_desired_json(movie, stream_info, CONFIG)
                all_movies.append(formatted)
                movies_map[str(mid)] = len(all_movies) - 1
                print(f"[Success! {formatted['resolution']}]", flush=True)

        # Anti-Loop Detection
        if processed_this_page == 0:
            print("🛑 [Loop Detected] Server is returning duplicate pages. Ending scrape.", flush=True)
            break

        # Save to file incrementally
        with open(CONFIG['output_file'], 'w', encoding='utf-8') as f:
            json.dump(all_movies, f, ensure_ascii=False, indent=4)

        pages_scraped_in_batch += 1
        if CONFIG['cooldown_every_pages'] > 0 and (pages_scraped_in_batch % CONFIG['cooldown_every_pages'] == 0):
            print(f"\n☕ [Break] Hit {CONFIG['cooldown_every_pages']} pages. Pausing for {CONFIG['cooldown_seconds']} seconds...", flush=True)
            time.sleep(CONFIG['cooldown_seconds'])
        else:
            time.sleep(CONFIG['delay_ms'] / 1000.0)
            
        page += 1

    print("\n====================================================")
    print(f"[FINISHED] Total movies saved: {len(all_movies)}")
    print(f"File location: {CONFIG['output_file']}")
    print("====================================================")
