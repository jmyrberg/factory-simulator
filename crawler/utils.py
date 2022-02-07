"""Module for utility functions and classes."""


import io
import logging
import pickle
import requests

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


# Monkey patch, see https://github.com/pypa/pipenv/issues/2609
import webdriver_manager.utils
def console(text, bold=False): pass  # NOQA
webdriver_manager.utils.console = console  # NOQA

from webdriver_manager.chrome import ChromeDriverManager


logger = logging.getLogger(__name__)


def get_chromedriver(settings=None, options=None):
    if not options:
        options = Options()
        if not settings.get('DISABLE_HEADLESS', False):
            options.add_argument("--headless")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    driver.minimize_window()
    logging.getLogger('selenium').setLevel(logging.INFO)
    logging.getLogger('urllib3').setLevel(logging.INFO)
    return driver


def update_proxies():
    resp = requests.get(
        'https://proxylist.geonode.com/api/proxy-list?limit=50&'
        'page=1&sort_by=lastChecked&sort_type=desc')
    proxylines = [f'{d["ip"]}:{d["port"]}' for d in resp.json()['data']]
    with open('proxies.txt', 'w') as f:
        f.write('\n'.join(proxylines))
        logger.info('Proxies updated successfully!')
