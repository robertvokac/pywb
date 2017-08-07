from .base_config_test import BaseConfigTest, fmod

from .memento_fixture import *

from warcio.timeutils import timestamp_to_http_date


# ============================================================================
class TestMemento(MementoMixin, BaseConfigTest):
    @classmethod
    def setup_class(cls):
        super(TestMemento, cls).setup_class('config_test.yaml')

    def _assert_memento(self, resp, url, ts, fmod, dt=''):
        dt = dt or timestamp_to_http_date(ts)

        links = self.get_links(resp)

        assert MEMENTO_DATETIME in resp.headers
        assert resp.headers[MEMENTO_DATETIME] == dt

        # memento link
        assert self.make_memento_link(url, ts, dt, fmod) in links

        # timegate link
        assert self.make_timegate_link(url, fmod) in links

        # timemap link
        assert self.make_timemap_link(url) in links

        # original
        assert self.make_original_link(url) in links

        assert '/pywb/{1}{0}/{2}'.format(fmod, ts, url) in resp.headers['Content-Location']

    # Memento Pattern 2.2 (no redirect, 200 negotiation)
    def test_memento_top_frame(self):
        resp = self.testapp.get('/pywb/20140127171238/http://www.iana.org/')

        # Memento Headers
        # no vary header
        assert VARY not in resp.headers
        assert MEMENTO_DATETIME in resp.headers

        # memento link
        dt = 'Mon, 27 Jan 2014 17:12:38 GMT'
        url = 'http://www.iana.org/'

        links = self.get_links(resp)

        assert self.make_memento_link(url, '20140127171238', dt, 'mp_') in links

        #timegate link
        assert self.make_timegate_link(url, 'mp_') in links

        # Body
        assert '<iframe ' in resp.text
        assert '/pywb/20140127171238mp_/http://www.iana.org/' in resp.text, resp.text

    def test_memento_content_replay_exact(self, fmod):
        resp = self.get('/pywb/20140127171238{0}/http://www.iana.org/', fmod)

        self._assert_memento(resp, 'http://www.iana.org/', '20140127171238', fmod)

        assert VARY not in resp.headers

        # Body
        assert '"20140127171238"' in resp.text
        assert 'wb.js' in resp.text
        assert 'new _WBWombat' in resp.text, resp.text
        assert '/pywb/20140127171238{0}/http://www.iana.org/time-zones"'.format(fmod) in resp.text

    def test_memento_at_timegate_latest(self, fmod):
        """
        TimeGate with no Accept-Datetime header
        """

        fmod_slash = fmod + '/' if fmod else ''
        resp = self.get('/pywb/{0}http://www.iana.org/_css/2013.1/screen.css', fmod_slash)

        assert resp.headers[VARY] == 'accept-datetime'

        self._assert_memento(resp, 'http://www.iana.org/_css/2013.1/screen.css', '20140127171239', fmod)

    def test_memento_at_timegate(self, fmod):
        """
        TimeGate with Accept-Datetime header, not matching a memento exactly, no redirect
        """
        dt = 'Sun, 26 Jan 2014 20:08:04 GMT'

        request_dt = 'Sun, 26 Jan 2014 20:08:00 GMT'
        headers = {ACCEPT_DATETIME: request_dt}

        fmod_slash = fmod + '/' if fmod else ''
        resp = self.get('/pywb/{0}http://www.iana.org/_css/2013.1/screen.css', fmod_slash, headers=headers)

        assert resp.headers[VARY] == 'accept-datetime'

        self._assert_memento(resp, 'http://www.iana.org/_css/2013.1/screen.css', '20140126200804', fmod, dt)

    def test_302_memento(self, fmod):
        """
        Memento (capture) of a 302 response
        """
        resp = self.get('/pywb/20140128051539{0}/http://www.iana.org/domains/example', fmod)

        assert resp.status_int == 302

        assert VARY not in resp.headers

        self._assert_memento(resp, 'http://www.iana.org/domains/example', '20140128051539', fmod)

    def test_timemap(self):
        """
        Test application/link-format timemap
        """

        resp = self.testapp.get('/pywb/timemap/link/http://example.com?example=1')
        assert resp.status_int == 200
        assert resp.content_type == LINK_FORMAT

        resp.charset = 'utf-8'

        exp = """\
<http://localhost:80/pywb/timemap/link/http://example.com?example=1>; rel="self"; type="application/link-format"; from="Fri, 03 Jan 2014 03:03:21 GMT",
<http://localhost:80/pywb/mp_/http://example.com?example=1>; rel="timegate",
<http://example.com?example=1>; rel="original",
<http://example.com?example=1>; rel="memento"; datetime="Fri, 03 Jan 2014 03:03:21 GMT"; src="pywb:example.cdx",
<http://example.com?example=1>; rel="memento"; datetime="Fri, 03 Jan 2014 03:03:41 GMT"; src="pywb:example.cdx"
"""
        assert exp == resp.text

    def test_timemap_2(self):
        """
        Test application/link-format timemap total count
        """

        resp = self.testapp.get('/pywb/timemap/link/http://example.com')
        assert resp.status_int == 200
        assert resp.content_type == LINK_FORMAT

        lines = resp.text.split('\n')

        assert len(lines) == 7

    def test_timemap_error_not_found(self):
        resp = self.testapp.get('/pywb/timemap/link/http://example.com/x-not-found', status=404)
        assert resp.body == b''

    def test_timemap_error_invalid_format(self):
        resp = self.testapp.get('/pywb/timemap/foo/http://example.com', status=400)
        assert resp.json == {'message': 'output=foo not supported'}

    def test_error_bad_accept_datetime(self):
        """
        400 response for bad accept_datetime
        """
        headers = {ACCEPT_DATETIME: 'Sun'}
        resp = self.testapp.get('/pywb/http://www.iana.org/_css/2013.1/screen.css', headers=headers, status=400)
        assert resp.status_int == 400


