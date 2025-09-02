import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
from dateutil import parser
import logging
import re
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit
import os
from dotenv import load_dotenv
import google.generativeai as genai
import feedparser

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class NewsScraper:
    def __init__(self):
        # load .env once
        try:
            load_dotenv()
        except Exception:
            pass
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        self.today = datetime.now().date()
        try:
            window_days = int(os.environ.get('NEWS_WINDOW_DAYS', '3'))
        except Exception:
            window_days = 3
        if window_days < 1:
            window_days = 1
        if window_days > 30:
            window_days = 30
        self.start_date = (datetime.now() - timedelta(days=window_days)).date()
        self.news_items = []
        self.genai_model = None

    def _date_in_window(self, dt: datetime) -> bool:
        try:
            d = dt.date()
        except Exception:
            d = dt
        return self.start_date <= d <= self.today

    def _add_item(self, title: str, content: str, link: str, dt: datetime | None):
        # Skip titles with a single word
        if len((title or '').split()) <= 1:
            logger.debug(f"Skip single-word title: {title} ({link})")
            return
        self.news_items.append({
            'tytuł': title,
            'treść': content,
            'link': link,
            'data': (dt.date().isoformat() if isinstance(dt, datetime) else (dt.isoformat() if hasattr(dt, 'isoformat') else None))
        })

    def _extract_date_from_soup(self, soup):
        # 1) Meta daty (kilka wariantów)
        meta_props = [
            {'property': 'article:published_time'},
            {'property': 'article:modified_time'},
            {'property': 'og:published_time'},
            {'property': 'og:updated_time'},
            {'name': 'date'},
            {'name': 'pubdate'},
            {'itemprop': 'datePublished'},
            {'itemprop': 'dateModified'}
        ]
        for attrs in meta_props:
            meta_time = soup.find('meta', attrs=attrs)
            if meta_time and meta_time.get('content'):
                try:
                    return parser.parse(meta_time['content'])
                except Exception:
                    continue

        # 2) <time datetime> lub tekst w <time>
        for time_tag in soup.find_all('time'):
            dt_val = time_tag.get('datetime') or time_tag.get('content') or time_tag.get_text(strip=True)
            if not dt_val:
                continue
            try:
                return parser.parse(dt_val, dayfirst=True)
            except Exception:
                continue

        # 3) Szukaj dat w tekście (wiele formatów)
        full_text = soup.get_text(' ', strip=True)
        # dd/mm/yyyy
        m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", full_text)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y")
            except Exception:
                pass
        # dd.mm.yyyy
        m = re.search(r"\b(\d{1,2}\.\d{1,2}\.\d{4})\b", full_text)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d.%m.%Y")
            except Exception:
                pass
        # yyyy-mm-dd
        m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", full_text)
        if m:
            try:
                return datetime.strptime(m.group(1), "%Y-%m-%d")
            except Exception:
                pass
        # 1 września 2025 (polskie miesiące)
        months = {
            'stycznia': 1, 'lutego': 2, 'marca': 3, 'kwietnia': 4, 'maja': 5, 'czerwca': 6,
            'lipca': 7, 'sierpnia': 8, 'września': 9, 'pazdziernika': 10, 'października': 10,
            'listopada': 11, 'grudnia': 12
        }
        m = re.search(r"\b(\d{1,2})\s+(stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|pazdziernika|listopada|grudnia)\s+(\d{4})\b", full_text, re.IGNORECASE)
        if m:
            try:
                day = int(m.group(1))
                month = months[m.group(2).lower()]
                year = int(m.group(3))
                return datetime(year, month, day)
            except Exception:
                pass

        return None

    def _discover_links(self, base_url: str, soup: BeautifulSoup, max_links: int = 80, allow_substrings: list[str] | None = None, allow_regex: str | None = None, deny_ext: tuple[str, ...] = ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.zip', '.doc', '.docx', '.xls', '.xlsx')):
        base_netloc = urlparse(base_url).netloc
        links = []
        regex_compiled = re.compile(allow_regex) if allow_regex else None
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('mailto:') or href.startswith('tel:') or href.startswith('javascript:'):
                continue
            abs_url = urljoin(base_url, href)
            # strip fragment
            sp = urlsplit(abs_url)
            abs_url = urlunsplit((sp.scheme, sp.netloc, sp.path, sp.query, ''))
            if urlparse(abs_url).netloc != base_netloc:
                continue
            if any(abs_url.lower().endswith(ext) for ext in deny_ext):
                continue
            if allow_substrings and not any(s in abs_url for s in allow_substrings):
                continue
            if regex_compiled and not regex_compiled.search(abs_url):
                continue
            # Skip edunews listing pages with pagination
            if 'edunews.pl' in base_netloc and 'aktualnosci' in abs_url and 'start=' in abs_url:
                continue
            if abs_url not in links:
                links.append(abs_url)
            if len(links) >= max_links:
                break
        logger.debug(f"Discovered {len(links)} links from {base_url}")
        return links

    def _extract_title_and_content(self, soup: BeautifulSoup, url: str):
        # Title
        title_elem = soup.find('h1') or soup.find('title')
        title = title_elem.get_text(strip=True) if title_elem else 'Brak tytułu'
        content = self._extract_main_text(soup, url)
        return title, content

    def _is_probably_article(self, soup: BeautifulSoup, url: str) -> bool:
        # Check OpenGraph type
        og_type = soup.find('meta', attrs={'property': 'og:type'})
        if og_type and 'article' in (og_type.get('content') or '').lower():
            return True
        # Schema.org Article
        if soup.find(attrs={'itemtype': re.compile('Article', re.I)}):
            return True
        # Presence of <article> with h1 and multiple paragraphs
        art = soup.find('article')
        if art:
            has_h1 = art.find('h1') is not None
            num_p = len(art.find_all('p'))
            if has_h1 and num_p >= 3:
                return True
        # Fallback: main with multiple paragraphs
        main = soup.find('main')
        if main and len(main.find_all('p')) >= 3:
            return True
        # Some WP/Drupal use class names
        if soup.find('div', class_=re.compile('(entry-content|article-body|field--name-body)', re.I)):
            return True
        return False

    def _clean_soup(self, soup: BeautifulSoup) -> None:
        # remove scripts/styles and common chrome
        for sel in ['script', 'style', 'noscript', 'iframe', 'form']:
            for el in soup.select(sel):
                el.decompose()
        chrome_selectors = [
            'header', 'footer', 'nav', 'aside', '.breadcrumb', '.breadcrumbs',
            '.menu', '.navbar', '.sidebar', '.pagination', '.pager', '.cookie', '.cookies'
        ]
        for sel in chrome_selectors:
            for el in soup.select(sel):
                el.decompose()

    def _extract_main_text(self, soup: BeautifulSoup, url: str) -> str:
        self._clean_soup(soup)
        domain = urlparse(url).netloc
        candidates: list[tuple[str, list[str]]] = []
        if 'edunews.pl' in domain:
            candidates = [
                ('div', ['itemFullText']),  # Joomla content
                ('div', ['content']),
                ('div', ['article-body']),
                ('div', ['articleContent']),
                ('div', ['itemprop=articleBody'])
            ]
        elif 'frse.org.pl' in domain:
            candidates = [
                ('div', ['field--name-body']),  # Drupal body
                ('div', ['node__content']),
                ('article', []),
                ('div', ['entry-content']),
                ('div', ['content'])
            ]
        elif 'youth.europa.eu' in domain:
            candidates = [
                ('div', ['field--name-body']),  # Drupal body
                ('article', []),
                ('main', [])
            ]
        elif 'ibe.edu.pl' in domain:
            candidates = [
                ('div', ['entry-content']),
                ('article', []),
                ('main', [])
            ]
        # Try candidates
        for tag, classes in candidates:
            if classes:
                for cls in classes:
                    if 'itemprop=' in cls:
                        itemprop = cls.split('=', 1)[1]
                        node = soup.find(tag, attrs={'itemprop': itemprop})
                    else:
                        node = soup.find(tag, class_=re.compile(cls))
                    if node:
                        parts = []
                        parts.extend(p.get_text(strip=True) for p in node.find_all('p'))
                        parts.extend(li.get_text(strip=True) for li in node.find_all('li'))
                        text = '\n\n'.join([t for t in parts if t])
                        if len(text) > 400 and text.count('.') >= 3:
                            return text
            else:
                node = soup.find(tag)
                if node:
                    parts = []
                    parts.extend(p.get_text(strip=True) for p in node.find_all('p'))
                    parts.extend(li.get_text(strip=True) for li in node.find_all('li'))
                    text = '\n\n'.join([t for t in parts if t])
                    if len(text) > 400 and text.count('.') >= 3:
                        return text
        # Generic fallback: all paragraphs under article/main/body
        scope = soup.find('article') or soup.find('main') or soup
        paras = scope.find_all(['p', 'li']) if scope else soup.find_all(['p', 'li'])
        text = '\n\n'.join(el.get_text(strip=True) for el in paras)
        return text

    def _fetch_sitemaps_from_robots(self, base_url: str):
        robots = urljoin(base_url, '/robots.txt')
        try:
            logger.debug(f"Fetching robots: {robots}")
            r = requests.get(robots, headers=self.headers, timeout=15)
            r.raise_for_status()
            sitemaps = []
            for line in r.text.splitlines():
                if line.lower().startswith('sitemap:'):
                    sm = line.split(':', 1)[1].strip()
                    sitemaps.append(sm)
            logger.debug(f"Found {len(sitemaps)} sitemaps in robots")
            return sitemaps
        except Exception as e:
            logger.debug(f"No robots or sitemaps for {base_url}: {e}")
            return []

    def _fetch_sitemap_links(self, sitemap_url: str):
        try:
            logger.debug(f"Fetch sitemap: {sitemap_url}")
            r = requests.get(sitemap_url, headers=self.headers, timeout=20)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'xml')
            links = []
            # sitemap index
            for sm in soup.find_all('sitemap'):
                loc = sm.find('loc')
                if loc and loc.text:
                    links.extend(self._fetch_sitemap_links(loc.text.strip()))
            # urlset
            for url in soup.find_all('url'):
                loc = url.find('loc')
                if not loc or not loc.text:
                    continue
                lastmod = None
                lm = url.find('lastmod')
                if lm and lm.text:
                    try:
                        lastmod = parser.parse(lm.text.strip())
                    except Exception:
                        lastmod = None
                links.append((loc.text.strip(), lastmod))
            return links
        except Exception as e:
            logger.debug(f"Sitemap fetch failed {sitemap_url}: {e}")
            return []

    def _process_article(self, url: str):
        try:
            resp = requests.get(url, headers=self.headers, timeout=20)
            resp.raise_for_status()
            ctype = resp.headers.get('Content-Type', '')
            if 'text/html' not in ctype:
                logger.debug(f"Skip non-HTML {url} ({ctype})")
                return False
            soup = BeautifulSoup(resp.text, 'html.parser')
            dt = self._extract_date_from_soup(soup)
            logger.debug(f"Article {url} date extracted: {dt}")
            if not dt or not self._date_in_window(dt):
                return False
            if not self._is_probably_article(soup, url):
                return False
            title, content = self._extract_title_and_content(soup, url)
            if len(content) < 200:
                # likely teaser/category – skip
                return False
            self._add_item(title, content, url, dt)
            logger.info(f"Added from crawl: {title}")
            return True
        except Exception as e:
            logger.debug(f"Skip article {url}: {e}")
            return False

    def _render_html(self, url: str) -> str | None:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            logger.debug(f"Playwright not available: {e}")
            return None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(locale='pl-PL', user_agent=self.headers.get('User-Agent'))
                page = context.new_page()
                page.set_default_timeout(20000)
                page.goto(url, wait_until='networkidle')
                # Poczekaj aż pojawią się linki do newsów
                try:
                    page.wait_for_selector('a[href*="/news/"]', timeout=10000)
                except Exception:
                    pass
                # Delikatny scroll, by zainicjować lazy-load (jeśli jest)
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            logger.debug(f"Playwright render failed for {url}: {e}")
            return None

    def crawl_from_listing(self, list_url: str, allow_substrings: list[str] | None = None, allow_regex: str | None = None):
        try:
            r = requests.get(list_url, headers=self.headers, timeout=20)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')
            links = self._discover_links(list_url, soup, allow_substrings=allow_substrings, allow_regex=allow_regex)
            # Fallback: jeśli brak linków (np. treść ładowana JS), spróbuj Playwright
            if not links:
                rendered = self._render_html(list_url)
                if rendered:
                    soup_js = BeautifulSoup(rendered, 'html.parser')
                    links = self._discover_links(list_url, soup_js, allow_substrings=allow_substrings, allow_regex=allow_regex)
            added = 0
            for i, link in enumerate(links, 1):
                if self._process_article(link):
                    added += 1
            logger.info(f"Crawl from {list_url}: added {added} articles")
        except Exception as e:
            logger.error(f"Crawl failed for {list_url}: {e}")

    def _parse_feed(self, feed_url: str, source_name: str):
        try:
            logger.debug(f"Fetching feed: {feed_url}")
            fp = feedparser.parse(feed_url)
            count_before = len(self.news_items)
            for entry in fp.entries:
                # Determine date
                dt = None
                for key in ['published', 'updated', 'created']:
                    if key in entry:
                        try:
                            dt = parser.parse(getattr(entry, key))
                            break
                        except Exception:
                            continue
                if not dt and 'published_parsed' in entry and entry.published_parsed:
                    dt = datetime(*entry.published_parsed[:6])
                if not dt:
                    continue
                if not self._date_in_window(dt):
                    continue

                title = entry.title if 'title' in entry else source_name
                link = entry.link if 'link' in entry else ''
                summary = ''
                if 'summary' in entry and entry.summary:
                    summary = BeautifulSoup(entry.summary, 'html.parser').get_text(strip=True)
                elif 'content' in entry and entry.content:
                    summary = BeautifulSoup(entry.content[0].value, 'html.parser').get_text(strip=True)

                self._add_item(title, summary, link)
            logger.info(f"Feed {source_name}: added {len(self.news_items)-count_before} items")
        except Exception as e:
            logger.warning(f"Feed parse failed for {feed_url}: {e}")

    def scrape_edunews(self):
        self.crawl_from_listing(
            "https://edunews.pl/aktualnosci",
            allow_substrings=[
                "/system-edukacji/",
                "/narzedzia-i-projekty/",
                "/edukacja-na-co-dzien/",
                "/nowoczesna-edukacja/",
                "/badania-i-debaty/",
                "/wydarzenia/"
            ],
            # Edunews artykuły mają w ścieżce segment z ID, np. /7166-tytul
            allow_regex=r"https?://[^/]*edunews\.pl/.+?/\d{3,}-"
        )

    def scrape_frse(self):
        # Zbuduj URL z parametrami i crawl
        list_url = "https://www.frse.org.pl/aktualnosci"
        self.crawl_from_listing(list_url, allow_substrings=["/aktualnosci/"])
        # Dodatkowo wydarzenia (opcjonalnie):
        self.crawl_from_listing("https://www.frse.org.pl/wydarzenia-i-szkolenia", allow_substrings=["/wydarzenia-i-szkolenia/"])

    def scrape_youth_europa(self):
        base = "https://youth.europa.eu"
        # 1) spróbuj sitemap
        all_sitemaps = self._fetch_sitemaps_from_robots(base)
        # fallback: dobrze znane ścieżki sitemap jeśli robots nic nie zwraca
        if not all_sitemaps:
            candidates = [
                urljoin(base, "/sitemap.xml"),
                urljoin(base, "/sitemap_index.xml"),
                urljoin(base, "/sitemap-index.xml"),
                urljoin(base, "/sitemap-news.xml"),
                urljoin(base, "/sitemap_news.xml"),
                urljoin(base, "/news/sitemap.xml"),
                urljoin(base, "/pl/sitemap.xml"),
            ]
            all_sitemaps.extend(candidates)
        news_candidates: list[tuple[str, datetime | None]] = []
        for sm in all_sitemaps:
            news_candidates.extend([item for item in self._fetch_sitemap_links(sm) if '/news/' in item[0]])
        # prefer język polski _pl
        news_candidates = [item for item in news_candidates if item[0].endswith('_pl')]
        # sortuj po lastmod malejąco
        news_candidates.sort(key=lambda x: (x[1] or datetime.min), reverse=True)
        # odfiltruj oknem dat jeśli mamy lastmod
        filtered = []
        for url, lastmod in news_candidates:
            if lastmod is None or self._date_in_window(lastmod):
                filtered.append(url)
            if len(filtered) >= 80:
                break
        logger.debug(f"Youth sitemap candidates: {len(filtered)}")
        added = 0
        for u in filtered:
            if self._process_article(u):
                added += 1
        # 2) fallback: listing crawl (gdyby sitemap nic nie dał)
        if added == 0:
            self.crawl_from_listing("https://youth.europa.eu/news_pl", allow_substrings=["/news/"])

    def scrape_ibe(self):
        self.crawl_from_listing("https://ibe.edu.pl/pl/aktualnosci", allow_substrings=["/pl/aktualnosci/"])

    def save_to_json(self):
        output_file = f"news_{self.start_date}_to_{self.today}.json"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.news_items, f, ensure_ascii=False, indent=4)
            logger.info(f"Saved {len(self.news_items)} news items to {output_file}")
        except Exception as e:
            logger.error(f"Error saving to JSON: {e}")

    # ===== Gemini integration =====
    def _ensure_gemini(self):
        if self.genai_model is not None:
            return
        api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise RuntimeError('Brak klucza API: ustaw zmienną środowiskową GOOGLE_API_KEY lub GEMINI_API_KEY')
        genai.configure(api_key=api_key)
        # Official model name requested: gemini-2.5-flash
        self.genai_model = genai.GenerativeModel('gemini-2.5-flash')

    def enrich_with_gemini(self):
        try:
            self._ensure_gemini()
        except Exception as e:
            logger.error(f"Gemini init failed: {e}")
            return
        for item in self.news_items:
            if item.get('gemini_tytul') and item.get('gemini_tresc'):
                continue
            original_title = item.get('tytuł', '')
            date_str = item.get('data', '')
            link = item.get('link', '')
            text = item.get('treść', '')
            # Trim very long content to keep response fast
            if len(text) > 12000:
                text = text[:12000]
            start_ts = datetime.now()
            logger.info(f"Gemini start for: {link}")
            prompt = (
                "Jesteś rzetelnym redaktorem. Na podstawie dostarczonej treści artykułu napisz nowy tytuł "
                "oraz artykuł w 4-5 akapitach. Używaj wyłącznie informacji zawartych w tekście, bez dopowiadania. "
                "Zwróć wynik w JSON z polami: gemini_tytul, gemini_tresc. Treść sformatuj w akapity oddzielone pustą linią.\n\n"
                f"TYTUL_ORG: {original_title}\n"
                f"DATA: {date_str}\n"
                f"LINK: {link}\n"
                f"TEKST: {text}"
            )
            try:
                resp = self.genai_model.generate_content(
                    prompt,
                    generation_config={'response_mime_type': 'application/json'}
                )
                resp_text = getattr(resp, 'text', '') or ''
                parsed_title = None
                parsed_body = None
                # Strip markdown code fences if present
                fenced = resp_text.strip()
                if fenced.startswith('```'):
                    # remove first fence line
                    lines = fenced.splitlines()
                    # drop first and last triple-backticks if present
                    if lines and lines[0].startswith('```'):
                        lines = lines[1:]
                    if lines and lines[-1].startswith('```'):
                        lines = lines[:-1]
                    resp_text = '\n'.join(lines)
                # Try strict JSON parse on the largest object span
                try:
                    start = resp_text.find('{')
                    end = resp_text.rfind('}')
                    if start != -1 and end != -1 and end > start:
                        payload = json.loads(resp_text[start:end+1])
                        parsed_title = (payload.get('gemini_tytul') or payload.get('gemini_title'))
                        parsed_body = (payload.get('gemini_tresc') or payload.get('gemini_content'))
                except Exception:
                    pass
                # Fallback heuristic if JSON parse failed
                if not parsed_title or not parsed_body:
                    lines = [ln.strip() for ln in resp_text.splitlines() if ln.strip()]
                    if lines:
                        parsed_title = parsed_title or lines[0][:200]
                        parsed_body = parsed_body or '\n\n'.join(lines[1:])
                if parsed_title and parsed_body:
                    item['gemini_tytul'] = parsed_title
                    item['gemini_tresc'] = parsed_body
                    elapsed = (datetime.now() - start_ts).total_seconds()
                    logger.info(f"Gemini done for: {link} in {elapsed:.2f}s")
                else:
                    logger.debug(f"Gemini returned unparseable content for {link}")
            except Exception as e:
                logger.error(f"Gemini enrichment failed for {link}: {e}")

def main():
    scraper = NewsScraper()
    # Uruchom wszystkie crawlery
    scraper.scrape_edunews()
    scraper.scrape_frse()
    scraper.scrape_youth_europa()
    scraper.scrape_ibe()
    # Enrichment via Gemini
    scraper.enrich_with_gemini()
    scraper.save_to_json()

if __name__ == "__main__":
    main()
