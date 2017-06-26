import re

class JSONPRewriter(object):
    JSONP = re.compile(r'^(\w+)\(\{')
    CALLBACK = re.compile(r'[?].*callback=([^&]+)')

    def __init__(self, urlrewriter):
        self.urlrewriter = urlrewriter

    def rewrite(self, string):
        # see if json is jsonp, starts with callback func
        m_json = self.JSONP.search(string)
        if not m_json:
            return string

        # see if there is a callback param in current url
        m_callback = self.CALLBACK.search(self.urlrewriter.wburl.url)
        if not m_callback:
            return string

        string = m_callback.group(1) + string[m_json.end(1):]
        return string

    def close(self):
        return ''



