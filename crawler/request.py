"""Module for custom Scrapy request components."""


from scrapy import Request


class SeleniumRequest(Request):

    def __init__(self, *args, driver_func=None, **kwargs):
        meta = kwargs.pop('meta', {}) or {}
        if 'driver_func' not in meta:
            meta['driver_func'] = driver_func
        new_kwargs = dict(**kwargs, meta=meta)
        super(SeleniumRequest, self).__init__(*args, **new_kwargs)
