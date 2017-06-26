import json
import os
import tempfile
import shutil
import yaml
import time

from fakeredis import FakeStrictRedis
from mock import patch

from pywb.webagg.aggregator import SimpleAggregator
from pywb.webagg.app import ResAggApp
from pywb.webagg.handlers import DefaultResourceHandler
from pywb.webagg.indexsource import LiveIndexSource, MementoIndexSource

from pywb.urlrewrite.geventserver import GeventServer

from pywb import get_test_dir
from pywb.utils.wbexception import NotFoundException


# ============================================================================
def to_json_list(cdxlist, fields=['timestamp', 'load_url', 'filename', 'source']):
    return list([json.loads(cdx.to_json(fields)) for cdx in cdxlist])

def key_ts_res(cdxlist, extra='filename'):
    return '\n'.join([cdx['urlkey'] + ' ' + cdx['timestamp'] + ' ' + cdx[extra] for cdx in cdxlist])

def to_path(path):
    if os.path.sep != '/':
        path = path.replace('/', os.path.sep)

    return path


# ============================================================================
TEST_CDX_PATH = to_path(get_test_dir() + '/cdxj/')
TEST_WARC_PATH = to_path(get_test_dir() + '/warcs/')


# ============================================================================
class BaseTestClass(object):
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass


# ============================================================================
PUBSUBS = []

class FakeStrictRedisSharedPubSub(FakeStrictRedis):
    def __init__(self, *args, **kwargs):
        super(FakeStrictRedisSharedPubSub, self).__init__(*args, **kwargs)
        self._pubsubs = PUBSUBS


# ============================================================================
class FakeRedisTests(object):
    @classmethod
    def setup_class(cls):
        super(FakeRedisTests, cls).setup_class()
        cls.redismock = patch('redis.StrictRedis', FakeStrictRedisSharedPubSub)
        cls.redismock.start()

    @staticmethod
    def add_cdx_to_redis(filename, key, redis_url='redis://localhost:6379/2'):
        r = FakeStrictRedis.from_url(redis_url)
        with open(filename, 'rb') as fh:
            for line in fh:
                r.zadd(key, 0, line.rstrip())

    @classmethod
    def teardown_class(cls):
        super(FakeRedisTests, cls).teardown_class()
        FakeStrictRedis().flushall()
        cls.redismock.stop()


# ============================================================================
class TempDirTests(object):
    @classmethod
    def setup_class(cls):
        super(TempDirTests, cls).setup_class()
        cls.root_dir = tempfile.mkdtemp()

    @classmethod
    def teardown_class(cls):
        super(TempDirTests, cls).teardown_class()
        shutil.rmtree(cls.root_dir)


# ============================================================================
class MementoOverrideTests(object):
    link_header_data = None
    orig_get_timegate_links = None

    @classmethod
    def setup_class(cls):
        super(MementoOverrideTests, cls).setup_class()

        # Load expected link headers
        MementoOverrideTests.link_header_data = None
        with open(to_path(get_test_dir() + '/text_content/link_headers.yaml')) as fh:
            MementoOverrideTests.link_header_data = yaml.load(fh)

        MementoOverrideTests.orig_get_timegate_links = MementoIndexSource.get_timegate_links

    @classmethod
    def mock_link_header(cls, test_name, load=False):
        def mock_func(self, params, closest):
            if load:
                res = cls.orig_get_timegate_links(self, params, closest)
                print(test_name + ': ')
                print("    '{0}': '{1}'".format(self.timegate_url, res))
                return res

            try:
                res = cls.link_header_data[test_name][self.timegate_url]
                time.sleep(0.2)
            except Exception as e:
                print(e)
                msg = self.timegate_url.format(url=params['url'])
                raise NotFoundException(msg)

            return res

        return mock_func


# ============================================================================
class LiveServerTests(object):
    @classmethod
    def setup_class(cls):
        super(LiveServerTests, cls).setup_class()
        #cls.server = ServerThreadRunner(cls.make_live_app())
        cls.server = GeventServer(cls.make_live_app())

    @staticmethod
    def make_live_app():
        app = ResAggApp()
        app.add_route('/live',
            DefaultResourceHandler(SimpleAggregator(
                                   {'live': LiveIndexSource()})
            )
        )
        return app

    @classmethod
    def teardown_class(cls):
        super(LiveServerTests, cls).teardown_class()
        cls.server.stop()
