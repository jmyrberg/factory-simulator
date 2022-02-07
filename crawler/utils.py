"""Module for utility functions and classes."""


import io
import logging
import pickle

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


# Monkey patch, see https://github.com/pypa/pipenv/issues/2609
import webdriver_manager.utils
def console(text, bold=False): pass  # NOQA
webdriver_manager.utils.console = console  # NOQA

from webdriver_manager.chrome import ChromeDriverManager


def get_chromedriver(settings=None, options=None):
    if not options:
        options = Options()
        if not settings.get('DISABLE_HEADLESS', False):
            options.add_argument("--headless")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    logging.getLogger('selenium').setLevel(logging.INFO)
    logging.getLogger('urllib3').setLevel(logging.INFO)
    return driver

