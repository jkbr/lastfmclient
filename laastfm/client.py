import json
from hashlib import md5
from urllib import urlencode

import requests

from .api import BaseClient
from .exceptions import ERRORS

try:
    from tornado.httpclient import AsyncHTTPClient, HTTPRequest
    has_async = True
except ImportError:
    has_async = False


API_URL = 'http://ws.audioscrobbler.com/2.0/'
AUTH_URL = 'http://www.last.fm/api/auth/?api_key={key}&cb={callback}'


class LastfmAPIError(Exception):

    def __init__(self, error, message):
        self.message = '[%s %s] %s' % (
            error,
            ERRORS.get(error, 'unknown error'),
            message
        )
        self.code = error
        self.msg = message

    def __str__(self):
        return self.message


class LastfmClient(BaseClient):

    api_key = None
    api_secret = None

    def __init__(self, api_key=None, api_secret=None, session_key=None):
        super(LastfmClient, self).__init__()

        if api_key:
            self.api_key = api_key
        if api_secret:
            self.api_secret = api_secret
        self.session_key = session_key

        assert self.api_key and self.api_secret, 'Missing API key or secret.'

    def get_auth_url(self, callback_url):
        return AUTH_URL.format(key=self.api_key, callback=callback_url)

    def _get_params(self, method, params, auth):

        if params is None:
            params = {}

        defaults = {
            'format': 'json',
            'api_key': self.api_key,
            'method': method,
        }

        params.update(defaults)
        params = {k: v for k, v in params.items()
                  if v is not None and k != 'callback'}

        getting_session = method == 'auth.getSession'
        auth = auth or (method == 'user.getInfo' and 'user' not in params)
        if auth or getting_session:
            if not getting_session:
                assert self.session_key, 'Missing session key.'
                params['sk'] = self.session_key
            params['api_sig'] = self._get_sig(params)
        return params

    def _get_sig(self, params):
        """See http://www.last.fm/api/authspec#8."""
        exclude = {'format', 'callback'}
        sig = ''.join(k + unicode(v).encode('utf8') for k, v
                      in sorted(params.items()) if k not in exclude)
        sig += self.api_secret
        return md5(sig).hexdigest()

    def _process_data(self, data):
        if 'error' in data:
            raise LastfmAPIError(**data)
        if isinstance(data, dict):
            keys = data.keys()
            if len(keys) == 1:
                return data[keys[0]]
        return data

    def call(self, http_method, method, auth, params):
        params = self._get_params(method, params, auth)
        data = requests.request(http_method, API_URL, params=params).json
        return self._process_data(data)


class AsyncLastfmClient(LastfmClient):

    def __init__(self, api_key=None, api_secret=None, session_key=None):
        super(AsyncLastfmClient, self).__init__(
            api_key, api_secret, session_key)
        if not has_async:
            raise RuntimeError('You need to install tornado.')

    @property
    def _async_client(self):
        return AsyncHTTPClient()

    def call(self, http_method, method, auth, params):

        url = API_URL

        callback = params.pop('callback')
        params = self._get_params(method, params, auth)
        params = urlencode({k: unicode(v).encode('utf8')
                            for k, v in params.items()})
        if http_method == 'POST':
            body = params
        else:
            body = None
            url = url + '?' + params

        def on_finish(response):
            data = self._process_data(json.loads(response.body))
            if callback:
                callback(data)

        self._async_client.fetch(
            url, method=http_method,
            body=body, callback=on_finish)
