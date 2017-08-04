import re
from pywb.rewrite.content_rewriter import StreamingRewriter


# =================================================================
def load_function(string):
    import importlib

    string = string.split(':', 1)
    mod = importlib.import_module(string[0])
    return getattr(mod, string[1])


# =================================================================
class RegexRewriter(StreamingRewriter):
    # @staticmethod
    # def comment_out(string):
    #    return '/*' + string + '*/'

    @staticmethod
    def format(template):
        return lambda string: template.format(string)

    @staticmethod
    def remove_https(string):
        return string.replace("https", "http")

    @staticmethod
    def add_prefix(prefix):
        return lambda string: prefix + string

    @staticmethod
    def archival_rewrite(rewriter):
        return lambda string: rewriter.rewrite(string)

    # @staticmethod
    # def replacer(other):
    #    return lambda m, string: other

    HTTPX_MATCH_STR = r'https?:\\?/\\?/[A-Za-z0-9:_@.-]+'

    # DEFAULT_OP = add_prefix

    def __init__(self, rewriter, rules):
        super(RegexRewriter, self).__init__(rewriter)
        # rules = self.create_rules(http_prefix)

        # Build regexstr, concatenating regex list
        regex_str = '|'.join(['(' + rx + ')' for rx, op, count in rules])

        # ensure it's not middle of a word, wrap in non-capture group
        regex_str = '(?<!\w)(?:' + regex_str + ')'

        self.regex = re.compile(regex_str, re.M)
        self.rules = rules

    def filter(self, m):
        return True

    def rewrite(self, string):
        return self.regex.sub(lambda x: self.replace(x), string)

    def replace(self, m):
        i = 0
        for _, op, count in self.rules:
            i += 1

            full_m = i
            while count > 0:
                i += 1
                count -= 1

            if not m.group(i):
                continue

            # Optional filter to skip matches
            if not self.filter(m):
                return m.group(0)

            # Custom func
            # if not hasattr(op, '__call__'):
            #    op = RegexRewriter.DEFAULT_OP(op)

            result = op(m.group(i))
            final_str = result

            # if extracting partial match
            if i != full_m:
                final_str = m.string[m.start(full_m):m.start(i)]
                final_str += result
                final_str += m.string[m.end(i):m.end(full_m)]

            return final_str

    @staticmethod
    def parse_rules_from_config(config):
        def run_parse_rules(rewriter):
            def parse_rule(obj):
                match = obj.get('match')
                if 'rewrite' in obj:
                    replace = RegexRewriter.archival_rewrite(rewriter)
                elif 'function' in obj:
                    replace = load_function(obj['function'])
                else:
                    replace = RegexRewriter.format(obj.get('replace', '{0}'))
                group = obj.get('group', 0)
                result = (match, replace, group)
                return result

            return list(map(parse_rule, config))

        return run_parse_rules


# =================================================================
class JSLinkRewriterMixin(object):
    """
    JS Rewriter which rewrites absolute http://, https:// and // urls
    at the beginning of a string
    """
    # JS_HTTPX = r'(?:(?:(?<=["\';])https?:)|(?<=["\']))\\{0,4}/\\{0,4}/[A-Za-z0-9:_@.-]+.*(?=["\s\';&\\])'
    # JS_HTTPX = r'(?<=["\';])(?:https?:)?\\{0,4}/\\{0,4}/[A-Za-z0-9:_@.\-/\\?&#]+(?=["\';&\\])'

    # JS_HTTPX = r'(?:(?<=["\';])https?:|(?<=["\']))\\{0,4}/\\{0,4}/[A-Za-z0-9:_@.-][^"\s\';&\\]*(?=["\';&\\])'
    JS_HTTPX = r'(?:(?<=["\';])https?:|(?<=["\']))\\{0,4}/\\{0,4}/[A-Za-z0-9:_@%.\\-]+/'

    def __init__(self, rewriter, rules=[]):
        rules = rules + [
            (self.JS_HTTPX, RegexRewriter.archival_rewrite(rewriter), 0)
        ]
        super(JSLinkRewriterMixin, self).__init__(rewriter, rules)


# =================================================================
class JSLocationRewriterMixin(object):
    """
    JS Rewriter mixin which rewrites location and domain to the
    specified prefix (default: 'WB_wombat_')
    """

    def __init__(self, rewriter, rules=[], prefix='WB_wombat_'):
        rules = rules + [
            (r'(?<![$\'"])\b(?:location|top)\b(?![$\'":])', RegexRewriter.add_prefix(prefix), 0),

            (r'(?<=[?])\s*(?:\w+[.])?(location)\s*(?=[:])', RegexRewriter.add_prefix(prefix), 1),

            (r'(?<=\.)postMessage\b\(', RegexRewriter.add_prefix('__WB_pmw(self.window).'), 0),

            (r'(?<=\.)frameElement\b', RegexRewriter.add_prefix(prefix), 0),
        ]
        super(JSLocationRewriterMixin, self).__init__(rewriter, rules)


# =================================================================
class JSWombatProxyRewriterMixin(object):
    """
    JS Rewriter mixin which wraps the contents of the
    script in an anonymous block scope and inserts
    Wombat js-proxy setup
    """

    local_init_func = '\nvar {0} = function(name) {{\
return (self._wb_wombat && self._wb_wombat.local_init &&\
 self._wb_wombat.local_init(name)) || self[name]; }}\n\
if (!self.__WB_pmw) {{ self.__WB_pmw = function(obj) {{ return obj; }} }}\n\
{{\n'

    local_init_func_name = '_____WB$wombat$assign$function_____'

    local_var_line = 'let {0} = {1}("{0}");'

    local_objs = ['window',
                  'self',
                  'document',
                  'location',
                  'top',
                  'parent',
                  'frames',
                  'opener']

    def __init__(self, rewriter, rules=[]):
        rules = rules + [
           (r'Function\(["\']return this["\']\)', RegexRewriter.format('Function("return this._WB_wombat_obj_proxy || this")'), 0),
           (r'(?<=\.)postMessage\b\(', RegexRewriter.add_prefix('__WB_pmw(self).'), 0),
        ]

        super(JSWombatProxyRewriterMixin, self).__init__(rewriter, rules)

        local_declares = '\n'.join([self.local_var_line.format(obj, self.local_init_func_name) for obj in self.local_objs])

        self.first_buff = self.local_init_func.format(self.local_init_func_name) + local_declares

        self.close_string = '\n\n}'

    def final_read(self):
        return self.close_string


# =================================================================
class JSLocationOnlyRewriter(JSLocationRewriterMixin, RegexRewriter):
    pass


# =================================================================
class JSLinkOnlyRewriter(JSLinkRewriterMixin, RegexRewriter):
    pass


# =================================================================
class JSLinkAndLocationRewriter(JSLocationRewriterMixin,
                                JSLinkRewriterMixin,
                                RegexRewriter):
    pass


# =================================================================
class JSNoneRewriter(RegexRewriter):
    def __init__(self, rewriter, rules=[]):
        super(JSNoneRewriter, self).__init__(rewriter, rules)


# =================================================================
class JSWombatProxyRewriter(JSWombatProxyRewriterMixin, RegexRewriter):
    pass


# =================================================================
# Set 'default' JSRewriter
JSRewriter = JSLinkAndLocationRewriter


# =================================================================
class XMLRewriter(RegexRewriter):
    def __init__(self, rewriter, extra=[]):
        rules = self._create_rules(rewriter)

        super(XMLRewriter, self).__init__(rewriter, rules)

    # custom filter to reject 'xmlns' attr
    def filter(self, m):
        attr = m.group(1)
        if attr and attr.startswith('xmlns'):
            return False

        return True

    def _create_rules(self, rewriter):
        return [
            ('([A-Za-z:]+[\s=]+)?["\'\s]*(' +
             RegexRewriter.HTTPX_MATCH_STR + ')',
             RegexRewriter.archival_rewrite(rewriter), 2),
        ]


# =================================================================
class CSSRewriter(RegexRewriter):
    CSS_URL_REGEX = "url\\s*\\(\\s*(?:[\\\\\"']|(?:&.{1,4};))*\\s*([^)'\"]+)\\s*(?:[\\\\\"']|(?:&.{1,4};))*\\s*\\)"

    CSS_IMPORT_NO_URL_REGEX = ("@import\\s+(?!url)\\(?\\s*['\"]?" +
                               "(?!url[\\s\\(])([\w.:/\\\\-]+)")

    def __init__(self, rewriter):
        rules = self._create_rules(rewriter)
        super(CSSRewriter, self).__init__(rewriter, rules)

    def _create_rules(self, rewriter):
        return [
            (CSSRewriter.CSS_URL_REGEX,
             RegexRewriter.archival_rewrite(rewriter), 1),

            (CSSRewriter.CSS_IMPORT_NO_URL_REGEX,
             RegexRewriter.archival_rewrite(rewriter), 1),
        ]
