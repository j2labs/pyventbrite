#! /usr/bin/env python
#
# pyventbrite - Python bindings for the Event Brite API
#

# This module's design is heavily influenced by the work of 
# Samuel Cormier-Iijima and team on the pyfacebook module.
# http://github.com/sciyoshi/pyfacebook/

"""
Python bindings for the Event Brite API
(pyventbrite - http://j2labs.net)

pyventbrite is a client library that wraps the Event Brite API.

For more information, see

Home Page: http://github.com/j2labs/pyventbrite
Developer: http://www.eventbrite.com/api/doc/

Pyvent Brite uses simplejson
http://undefined.org/python/#simplejson to download it
or use pip install simplejson
"""

import sys
import time
import struct
import urllib
import urllib2
import httplib
try:
    import hashlib
except ImportError:
    import md5 as hashlib
import binascii
import urlparse
import mimetypes

RESPONSE_JSON = 'json'
RESPONSE_FORMAT = RESPONSE_JSON
try:
    import simplejson
except ImportError:
    quit( 'pyventbrite requires simplejson')
        
def urlread(url, data=None):
    res = urllib2.urlopen(url, data=data)
    return res.read()

__all__ = ['Pyvent Brite']

VERSION = '0.1'

EVENTBRITE_URL = 'http://www.eventbrite.com/'
EVENTBRITE_SECURE_URL = 'https://www.eventbrite.com/'

class json(object): pass

# simple IDL for the Event Brite API
METHODS = {
    'events': {
        'event_get': [
            ('id', int, []),
        ],
        'event_list_attendees': [
            ('id', int, []),
        ],
    },
}

class Proxy(object):
    """Represents a "namespace" of Event Brite API calls."""

    def __init__(self, client, name):
        self._client = client
        self._name = name

    def __call__(self, method=None, args=None, add_session_args=True):
        # for Django templates
        if method is None:
            return self

        return self._client('%s' % (method), args)


# generate the EventBrite proxies
def __generate_proxies():
    for namespace in METHODS:
        methods = {}

        for method in METHODS[namespace]:
            params = ['self']
            body = ['args = {}']

            for param_name, param_type, param_options in METHODS[namespace][method]:
                param = param_name

                for option in param_options:
                    if isinstance(option, tuple) and option[0] == 'default':
                        if param_type == list:
                            param = '%s=None' % param_name
                            body.append('if %s is None: %s = %s' % (param_name, param_name, repr(option[1])))
                        else:
                            param = '%s=%s' % (param_name, repr(option[1]))

                if param_type == json:
                    # we only jsonify the argument if it's a list or a dict, for compatibility
                    body.append('if isinstance(%s, list) or isinstance(%s, dict): %s = simplejson.dumps(%s)' % ((param_name,) * 4))

                if 'optional' in param_options:
                    param = '%s=None' % param_name
                    body.append('if %s is not None: args[\'%s\'] = %s' % (param_name, param_name, param_name))
                else:
                    body.append('args[\'%s\'] = %s' % (param_name, param_name))

                params.append(param)

            # simple docstring to refer them to Event Brite API docs
            body.insert(0, '"""Event Brite API call. See http://www.eventbrite.com/api/doc/%s"""' % (method))

            body.insert(0, 'def %s(%s):' % (method, ', '.join(params)))

            body.append('return self(\'%s\', args)' % method)

            exec('\n    '.join(body))

            methods[method] = eval(method)

        proxy = type('%sProxy' % namespace.title(), (Proxy, ), methods)

        globals()[proxy.__name__] = proxy


__generate_proxies()


class EventBriteError(Exception):
    """Exception class for errors received from Event Brite."""

    def __init__(self, code, msg, args=None):
        self.code = code
        self.msg = msg
        self.args = args

    def __str__(self):
        return 'Error %s: %s' % (self.code, self.msg)

class EventBrite(object):
    """
    Provides access to the Event Brite API.

    Instance Variables:

    app_key
        Your application key, as set in the constructor.

    eventbrite_url
        The url to use for Event Brite requests.

    eventbrite_secure_url
        The url to use for secure Event Brite requests.

    user_key
        Your users key, required for some data

    ----------------------------------------------------------------------

    """

    def __init__(self, app_key, user_key=None, internal=None, proxy=None, eventbrite_url=None, eventbrite_secure_url=None):
        """
        Initializes a new EventBrite object which provides wrappers for the Event Brite API.
        """
        self.app_key = app_key
        self.user_key = user_key        
        self.session_key = None
        self.session_key_expires = None
        self.internal = internal
        self.proxy = proxy
        if eventbrite_url is None:
            self.eventbrite_url = EVENTBRITE_URL
        else:
            self.eventbrite_url = eventbrite_url
        if eventbrite_secure_url is None:
            self.eventbrite_secure_url = EVENTBRITE_SECURE_URL
        else:
            self.eventbrite_secure_url = eventbrite_secure_url

        for namespace in METHODS:
            self.__dict__[namespace] = eval('%sProxy(self, \'%s\')' % (namespace.title(), 'eventbrite.%s' % namespace))



    def _check_error(self, response):
        """Checks if the given Event Brite response is an error, and then raises the appropriate exception."""
        if type(response) is dict and response.has_key('error'):
            raise EventBriteError(response['error']['error_type'], response['error']['error_msg'], response['request_args'])


    def _build_query_args(self, method, args=None):
        """Adds to args parameters that are necessary for every call to the API."""
        if args is None:
            args = {}

        for arg in args.items():
            if type(arg[1]) == list:
                args[arg[0]] = ','.join(str(a) for a in arg[1])
            elif type(arg[1]) == unicode:
                args[arg[0]] = arg[1].encode("UTF-8")
            elif type(arg[1]) == bool:
                args[arg[0]] = str(arg[1]).lower()

        args['app_key'] = self.app_key
        if hasattr(self, 'user_key'):
            args['user_key'] = self.user_key

        return args


    def _parse_response(self, response, method, format=None):
        """Parses the response according to the given (optional) format, which should be 'json'."""

        if not format:
            format = RESPONSE_FORMAT

        if format == RESPONSE_JSON:
            result = simplejson.loads(response)
            self._check_error(result)
        else:
            raise RuntimeError('Invalid format specified.')

        return result


    def unicode_urlencode(self, params):
        """
        @author: houyr
        A unicode aware version of urllib.urlencode.
        """
        if isinstance(params, dict):
            params = params.items()
        return urllib.urlencode([(k, isinstance(v, unicode) and v.encode('utf-8') or v)
                          for k, v in params])


    def __call__(self, method=None, args=None, secure=False, format=RESPONSE_FORMAT):
        """Make a call to Event Brite's REST server."""
        # for Django templates, if this object is called without any arguments
        # return the object itself
        if method is None:
            return self

        # @author: houyr
        # fix for bug of UnicodeEncodeError
        #post_args = self.unicode_urlencode(self._build_post_args(method, args))
        get_args = self._build_query_args(method, args)
        if secure:
            query_url = self.get_query_url(self.eventbrite_secure_url, format, method, args)
        else:
            query_url = self.get_query_url(self.eventbrite_url, format, method, args)
        
        if self.proxy:
            proxy_handler = urllib2.ProxyHandler(self.proxy)
            opener = urllib2.build_opener(proxy_handler)
            response = opener.open(query_url).read()
        else:
            response = urlread(query_url)

        print 'QUERYURL :: %s' % query_url
        print 'RESPONSE :: %s' % response

        return self._parse_response(response, method)


    # URL helpers
    def get_query_url(self, url, format, method, get_args):
        """
        Returns one of the Event Brite URLs (www.eventbrite.com/format/method).
        Named arguments are passed as GET query string parameters.

        """
        return '%s%s/%s?%s' % (url, format, method, urllib.urlencode(get_args))



if __name__ == '__main__':
    app_key = ''
    user_key = ''
    event_id = ''

    eventbrite = EventBrite(app_key, user_key=user_key)

    eventbrite.events.event_get(event_id)
    eventbrite.events.event_list_attendees(event_id)
