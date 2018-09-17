from http.server import BaseHTTPRequestHandler
from inspect import getargspec
import json
import os.path
from pathlib import Path
import re
from urllib.parse import unquote

from .Session import Session, timestamp
from .Box import Box, ErrorBox
from .code import showCode, IllegalFilenameError
from .ResponseWriter import ResponseWriter
from .FrameworkException import FrameworkException
from .utils import *

try:
	from stasis import StasisError
except ImportError:
	class StasisError(BaseException): pass

handlers = {'get': {}, 'post': {}}
vueComponents, views = None, None

def makeWrapper(httpMethod, index, action, kw):
	def wrap(f):
		kw['fn'] = f
		handlers[httpMethod][re.compile("^%s$" % index), action] = kw
		return f
	return wrap

@globalize
def get(index, action = None, **kw):
	return makeWrapper('get', index, action, kw)

@globalize
def post(index, action = None, **kw):
	return makeWrapper('post', index, action, kw)

class HTTPHandler(BaseHTTPRequestHandler, object):
	def __init__(self, request, address, server):
		self.session = None
		self.title(None)
		self.contentType = 'text/html'
		self.forceDownload = False
		self.responseCode = 200
		BaseHTTPRequestHandler.__init__(self, request, address, server)

	def buildResponse(self, method, postData):
		self.handler = None
		self.method = method
		writer = ResponseWriter(True, bytes)

		try: # raise DoneRendering; starts here to catch self.error calls
			path = self.path
			query = {}
			queryStr = None

			# Add GET params to query
			if '?' in path:
				path, queryStr = path.split('?', 1)
				if queryStr != '':
					query = self.parseQueryString(queryStr)

			# Check GET params for a p_ prefix collision
			for key in query:
				if key[:2] == 'p_':
					self.error("Invalid request", "Illegal query key: %s" % key, code = 400)

			# Add POST params to query with a p_ prefix
			query.update(dict([('p_' + k, v) for (k, v) in postData.items()]))

			assert path[0] == '/'
			path = path[1:]
			if len(path) and path[-1] == '/': path = path[:-1]
			path = unquote(path)
			specAction = query.get('action', query.get('p_action', None))
			for (pattern, action), handler in handlers[method].items():
				match = pattern.match(path)
				if match:
					if action is not None:
						if action == specAction:
							if 'action' in query:
								del query['action']
							else:
								del query['p_action']
						else: # Wrong action specifier (or none provided; taking a SFINAE approach and assuming another matching route won't need it)
							continue
					self.handler = handler
					for k, v in list(match.groupdict().items()):
						if k in query:
							self.error("Invalid request", "Duplicate key in request: %s" % k, code = 400)
						query[k] = v
					break

			query = self.preprocessQuery(query)

			if self.handler is None:
				self.error("Invalid request", "Unknown %s action <b>%s%s</b>" % (method.upper(), path or '/', " [%s]" % specAction if specAction else ''), code = 404)

			self.path = '/' + path

			self.invokeHandler(self.handler, query)
		except DoneRendering: pass
		except StasisError as e:
			writer.clear()
			self.title('Database Error')
			self.error('Database Error', e.message, False, code = 500)
		except Redirect:
			writer.done()
			raise
		except:
			writer.start()
			self.unhandledError()

		self.response = writer.done()
		self.requestDone()
		# self.leftMenu.clear()

	def parseQueryString(self, query):
		# Adapted from urlparse.parse_qsl
		items = []
		for arg in query.split('&'):
			if not arg: continue
			parts = arg.split('=', 1)
			items.append([unquote(part.replace('+', ' ')) for part in parts])
		return self.parseQueryItems(items)

	def parseQueryItems(self, items):
		query = {}
		for i in items:
			k, v = (i[0], True) if len(i) == 1 else i

			match = re.match(('([^[]*)(\\[.*\\])'), k)
			if match:
				key, subKeys = match.groups()
				subKeys = re.findall('\\[([^\\]]*)\\]', subKeys)

				if key in query:
					if not isinstance(query[key], list if subKeys == [''] else dict):
						self.error("Invalid request", "Type conflict on query key %s" % key, code = 400)
				else:
					query[key] = [] if subKeys == [''] else {}

				base = query[key]
				for thisSubKey in subKeys[:-2]:
					if thisSubKey in base:
						if not isinstance(base[thisSubKey], dict):
							self.error("Invalid request", "Type conflict on query key %s, subkey %s" % (key, thisSubKey), code = 400)
					else:
						base[thisSubKey] = {}
					base = base[thisSubKey]

				type = list if subKeys[-1] == '' else dict
				if len(subKeys) >= 2:
					if subKeys[-2] in base:
						if not isinstance(base[subKeys[-2]], type):
							self.error("Invalid request", "Type conflict on query key %s, subkey %s" % (key, subKeys[-2]), code = 400)
					else:
						base[subKeys[-2]] = type()
					base = base[subKeys[-2]]

				if type == list:
					base.append(v)
				else:
					if subKeys[-1] in base:
						self.error("Invalid request", "Collision on query key %s, subkey %s" % (key, subKeys[-1]), code = 400)
					base[subKeys[-1]] = v
			else:
				if k in query:
					self.error("Invalid request", "Collision on query key %s" % k, code = 400)
				query[k] = v

		return query

	def sendHead(self, additionalHeaders = {}, includeCookie = True):
		headers = {
			'Content-type': self.contentType,
			'Content-Length': str(len(self.response)),
			'Last-Modified': self.date_time_string(),
		}
		if self.session:
			headers['Set-Cookie'] = 'session=%s; expires=%s; path=/' % (self.session.key, timestamp())
		if self.forceDownload:
			headers['Content-disposition'] = "attachment; filename=%s" % self.forceDownload

		headers.update(additionalHeaders)

		self.send_response(self.responseCode)
		for name, value in headers.items():
			self.send_header(name, value)
		self.end_headers()

	def handle_one_request(self):
		try:
			BaseHTTPRequestHandler.handle_one_request(self)
		except:
			self.response = str(FrameworkException(sys.exc_info())).encode('utf8')
			self.sendHead(includeCookie = False)
			self.wfile.write(self.response)
			raise

	def do_HEAD(self, method = 'get', postData = {}):
		self.session = Session.load(Session.determineKey(self))
		self.processingRequest()

		try:
			self.buildResponse(method, postData)
			self.sendHead()
		except Redirect as r:
			self.responseCode = 302
			self.response = bytes()
			self.sendHead(additionalHeaders = {'Location': r.target})

	def do_GET(self):
		self.do_HEAD('get')
		self.wfile.write(self.response)

	def do_POST(self):
		form = cgi.FieldStorage(fp = self.rfile, headers = self.headers, environ = {'REQUEST_METHOD': 'POST'}, keep_blank_values = True)
		data = {}
		try:
			items = []
			for k in form:
				if type(form[k]) is list:
					items += [(k, v.value) for v in form[k]]
				else:
					items.append((k, form[k].value))
			data = self.parseQueryItems(items)
		except DoneRendering: pass
		except TypeError: pass # Happens with empty forms
		self.do_HEAD('post', data)
		self.wfile.write(self.response)

	def error(self, title, text, isDone = True, code = None):
		print(ErrorBox(title, text))
		if code is not None:
			self.responseCode = code
		if isDone:
			done()

	def title(self, title): pass

	def processingRequest(self): pass

	def preprocessQuery(self, query): return query

	def preprocessViewData(self, data): return data

	def invokeHandler(self, handler, query):
		printData = 'view-data' in query
		if printData:
			del query['view-data']

		given = list(query.keys())
		expected, _, keywords, defaults = getargspec(handler['fn'])
		defaults = defaults or []

		if keywords is None:
			givenS, expectedS = set(given), set(expected)
			requiredS = set(expected[:-len(defaults)] if defaults else expected)

			expectedS -= {'self', 'handler'}
			requiredS -= {'self', 'handler'}

			over = givenS - expectedS
			if len(over):
				self.error("Invalid request", "Unexpected request argument%s: %s" % ('s' if len(over) > 1 else '', ', '.join(over)), code = 400)

			under = requiredS - givenS
			if len(under):
				self.error("Invalid request", "Missing expected request argument%s: %s" % ('s' if len(under) > 1 else '', ', '.join(under)), code = 400)

		if views is not None and 'view' in handler:
			# Error out early if the view doesn't exist
			self.view = views[handler['view']]

			# It's not expected that a view-based handler will print, but if it does we let it go out and print the view text after
			self.viewData = handler['fn'](handler = self, **query)
			if printData:
				self.viewData = {'viewData': self.viewData}
				print("<su-callout title=\"View Data\"><pre>{{ viewData }}</pre></su-callout>")
			else:
				print(self.view['html'])

			#NB: It's up to the app code to deal with view JS/CSS.
		else:
			handler['fn'](handler = self, **query)

	def requestDone(self): pass

	def unhandledError(self):
		self.title('Unhandled Error')
		print(Box('Unhandled Error', formatException(), clr = 'red'))
		# Find the first file that's within this project, starting from the top of the call stack
		base = basePath()
		for (filename, line, fn, stmt) in traceback.extract_tb(sys.exc_info()[2])[::-1]:
			if filename.startswith(base):
				try:
					showCode(filename, line, 5)
				except IllegalFilenameError as e:
					print(ErrorBox("Illegal filename", escapeTags(str(e))))
				return

	@staticmethod
	def enableStaticHandler(staticRoot):
		staticRoot = Path(staticRoot).resolve()
		# self.staticRoot = Path(staticRoot)
		@get('static/(?P<filename>.+)', name = 'static', allowGuest = True)
		def fn(handler, filename):
			types = {
				'.css': 'text/css',
				'.js': 'text/javascript',
				'.pdf': 'application/pdf',
				'.png': 'image/png',
				'.svg': 'image/svg+xml'
			}

			path = (staticRoot / filename).resolve()
			if not path.exists():
				return handler.error("Invalid static argument", f"Static resource <b>{escapeTags(filename)}</b> does not exist", False, code = 404)
			if staticRoot not in path.parents:
				return handler.error("Invalid static argument", f"Static resource <b>{escapeTags(filename)}</b> is not allowed", False, code = 403)

			_, ext = os.path.splitext(path)
			if ext in types:
				handler.contentType = types[ext]

			sys.stdout.write(path.read_bytes())

	@staticmethod
	def enableVue(componentDir, viewDir, componentRoute = None, viewRoute = None):
		from .Vue import VueComponents, Views
		global vueComponents, views
		vueComponents = VueComponents(componentDir, componentRoute)
		views = Views(viewDir, viewRoute)
