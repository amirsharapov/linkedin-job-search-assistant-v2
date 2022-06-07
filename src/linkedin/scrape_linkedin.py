from commons.helpers.logging import configure_path, log_info
from commons.helpers.threads import run_in_separate_thread
from commons.helpers.browser import open_tab
from commons.helpers.files import (
    safe_read_json_as_obj_from_file,
    ensure_path_exists,
    safe_write_obj_as_json_to_file
)


from logging import getLogger, ERROR
from time import sleep
from urllib.parse import unquote

from flask import Flask, request
from flask_cors import CORS

from src.fortune_500_handlers import get_top_tech_from_f500


getLogger('werkzeug').setLevel(ERROR)
configure_path('data/logs.txt')


PEOPLE_SEARCH_MAX_PAGES = 3
PEOPLE_SEARCH_URL = 'https://www.linkedin.com/search/results/people/?keywords={}&origin=CLUSTER_EXPANSION&page={}'
PEOPLE_SEARCH_POSITIONS = [
    'technical recruiter',
    'technical sourcer',
    'early career technical recruiter'
]


def build_search_query(company=None):
    if company:
        return ' OR '.join([f'{company} {position}' for position in PEOPLE_SEARCH_POSITIONS])
    return ' OR '.join(PEOPLE_SEARCH_POSITIONS)


class SearchResultsIndex:
    PATH = 'data/indices/search_results.json'

    def __init__(self):
        ensure_path_exists(self.PATH)
        self.data = safe_read_json_as_obj_from_file(self.PATH, {})

    def add(self, key, value):
        if key not in self.data:
            self.data[key] = value
            safe_write_obj_as_json_to_file(self.PATH, self.data)

    @staticmethod
    def build_key_from_search_query(search_query, page):
        search_query = search_query.lower().replace(" ", '_').replace('"', '')
        return f'{search_query}_{page}'

    @staticmethod
    def build_key_from_request_body(body):
        keywords = unquote(body['url_params']['keywords']).lower().replace(' ', '_').replace('"', '')
        page = body['url_params'].get('page', '1')
        return f'{keywords}_{page}'

    @staticmethod
    def build_prev_idx_key_from_curr_idx_key(idx_key: str, curr_page: int):
        return idx_key.replace(str(curr_page), str(curr_page - 1))


class RecruitersIndex:
    PATH = 'data/indices/recruiters.json'

    def __init__(self):
        ensure_path_exists(self.PATH)
        self.data = safe_read_json_as_obj_from_file(self.PATH, {})


companies = get_top_tech_from_f500()


app = Flask(__name__)
CORS(app)

search_results_index = SearchResultsIndex()
recruiters_index = RecruitersIndex()


@app.route('/save-html', methods=['POST'])
def save_html():
    body = request.json
    idx_key = search_results_index.build_key_from_request_body(body)

    if idx_key not in search_results_index.data:
        search_results_index.add(idx_key, body)
        log_info(f'IDX saved: {idx_key}')
    else:
        log_info(f'Received request with IDX key already indexed: {idx_key}')

    return 'OK', 200


def scrape_linkedin_search_results_pages():
    for page in range(1, PEOPLE_SEARCH_MAX_PAGES + 1):
        for company in companies:
            linkedin_search_query = build_search_query(company.lower())
            idx_key = search_results_index.build_key_from_search_query(linkedin_search_query, page)

            if idx_key in search_results_index.data:
                continue

            if page > 1:
                prev_page_idx_key = search_results_index.build_prev_idx_key_from_curr_idx_key(idx_key, page)
                prev_page_results = search_results_index.data.get(prev_page_idx_key, {}).get('results', [])

                if len(prev_page_results) == 0:
                    continue

            url = PEOPLE_SEARCH_URL.format(linkedin_search_query, page)

            open_tab(url)
            log_info(f'Opened URL: {idx_key}')

            sleep(3)


def scrape_linkedin():
    run_in_separate_thread(lambda: app.run(port=8082))
    scrape_linkedin_search_results_pages()
