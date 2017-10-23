from warcio.timeutils import timestamp_to_datetime, timestamp_to_sec
from warcio.timeutils import timestamp_now

from pywb.utils.loaders import load

from six.moves.urllib.parse import urlsplit

from jinja2 import Environment, TemplateNotFound
from jinja2 import FileSystemLoader, PackageLoader, ChoiceLoader

from webassets.ext.jinja2 import AssetsExtension
from webassets.loaders import YAMLLoader
from webassets.env import Resolver

from pkg_resources import resource_filename

import json
import os


# ============================================================================
class RelEnvironment(Environment):
    """Override join_path() to enable relative template paths."""
    def join_path(self, template, parent):
        return os.path.join(os.path.dirname(parent), template)


# ============================================================================
class JinjaEnv(object):
    def __init__(self, paths=['templates', '.', '/'],
                       packages=['pywb'],
                       assets_path=None,
                       globals=None,
                       overlay=None,
                       extensions=None,
                       env_template_params_key='pywb.template_params',
                       env_template_dir_key='pywb.templates_dir'):

        self._init_filters()

        loader = ChoiceLoader(self._make_loaders(paths, packages))

        self.env_template_params_key = env_template_params_key
        self.env_template_dir_key = env_template_dir_key

        extensions = extensions or []

        if assets_path:
            extensions.append(AssetsExtension)

        if overlay:
            jinja_env = overlay.jinja_env.overlay(loader=loader,
                                                  trim_blocks=True,
                                                  extensions=extensions)
        else:
            jinja_env = RelEnvironment(loader=loader,
                                       trim_blocks=True,
                                       extensions=extensions)

        jinja_env.filters.update(self.filters)

        if globals:
            jinja_env.globals.update(globals)

        self.jinja_env = jinja_env

        # init assets
        if assets_path:
            assets_loader = YAMLLoader(load(assets_path))
            assets_env = assets_loader.load_environment()
            assets_env.resolver = PkgResResolver()
            jinja_env.assets_environment = assets_env

    def _make_loaders(self, paths, packages):
        loaders = []
        # add loaders for paths
        for path in paths:
            loaders.append(FileSystemLoader(path))

        # add loaders for all specified packages
        for package in packages:
            loaders.append(PackageLoader(package))

        return loaders

    def template_filter(self, param=None):
        def deco(func):
            name = param or func.__name__
            self.filters[name] = func
            return func

        return deco

    def _init_filters(self):
        self.filters = {}

        @self.template_filter()
        def format_ts(value, format_='%a, %b %d %Y %H:%M:%S'):
            if format_ == '%s':
                return timestamp_to_sec(value)
            else:
                value = timestamp_to_datetime(value)
                return value.strftime(format_)

        @self.template_filter('urlsplit')
        def get_urlsplit(url):
            split = urlsplit(url)
            return split

        @self.template_filter()
        def tojson(obj):
            return json.dumps(obj)


# ============================================================================
class BaseInsertView(object):
    def __init__(self, jenv, insert_file, banner_view=None):
        self.jenv = jenv
        self.insert_file = insert_file
        self.banner_view = banner_view

    def render_to_string(self, env, **kwargs):
        template = None
        template_path = env.get(self.jenv.env_template_dir_key)

        if template_path:
            # jinja paths are not os paths, always use '/' as separator
            # https://github.com/pallets/jinja/issues/411
            template_path = template_path + '/' + self.insert_file

            try:
                template = self.jenv.jinja_env.get_template(template_path)
            except TemplateNotFound as te:
                pass

        if not template:
            template = self.jenv.jinja_env.get_template(self.insert_file)

        params = env.get(self.jenv.env_template_params_key)
        if params:
            kwargs.update(params)
        kwargs['env'] = env

        return template.render(**kwargs)


# ============================================================================
class HeadInsertView(BaseInsertView):
    def create_insert_func(self, wb_url,
                           wb_prefix,
                           host_prefix,
                           top_url,
                           env,
                           is_framed,
                           coll='',
                           include_ts=True,
                           **kwargs):

        params = kwargs
        params['host_prefix'] = host_prefix
        params['wb_prefix'] = wb_prefix
        params['wb_url'] = wb_url
        params['top_url'] = top_url
        params['coll'] = coll
        params['is_framed'] = 'true' if is_framed else 'false'

        def make_head_insert(rule, cdx):
            params['wombat_ts'] = cdx['timestamp'] if include_ts else ''
            params['wombat_sec'] = timestamp_to_sec(cdx['timestamp'])
            params['is_live'] = 'true' if cdx.get('is_live') else 'false'

            if self.banner_view:
                banner_html = self.banner_view.render_to_string(env, cdx=cdx, **params)
                params['banner_html'] = banner_html

            return self.render_to_string(env, cdx=cdx, **params)

        return make_head_insert


# ============================================================================
class TopFrameView(BaseInsertView):
    def get_top_frame(self, wb_url,
                      wb_prefix,
                      host_prefix,
                      env,
                      frame_mod,
                      replay_mod,
                      coll='',
                      extra_params=None):

        embed_url = wb_url.to_str(mod=replay_mod)

        if wb_url.timestamp:
            timestamp = wb_url.timestamp
        else:
            timestamp = timestamp_now()

        is_proxy = 'wsgiprox.proxy_host' in env

        params = {'host_prefix': host_prefix,
                  'wb_prefix': wb_prefix,
                  'wb_url': wb_url,
                  'coll': coll,

                  'options': {'frame_mod': frame_mod,
                              'replay_mod': replay_mod},

                  'embed_url': embed_url,
                  'is_proxy': is_proxy,
                  'timestamp': timestamp,
                  'url': wb_url.get_url()
                 }

        if extra_params:
            params.update(extra_params)

        if self.banner_view:
            banner_html = self.banner_view.render_to_string(env, **params)
            params['banner_html'] = banner_html

        return self.render_to_string(env, **params)


# ============================================================================
class PkgResResolver(Resolver):
    def get_pkg_path(self, item):
        if not isinstance(item, str):
            return None

        parts = urlsplit(item)
        if parts.scheme == 'pkg' and parts.netloc:
            return (parts.netloc, parts.path)

        return None

    def resolve_source(self, ctx, item):
        pkg = self.get_pkg_path(item)
        if pkg:
            filename = resource_filename(pkg[0], pkg[1])
            if filename:
                return filename

        return super(PkgResResolver, self).resolve_source(ctx, item)


