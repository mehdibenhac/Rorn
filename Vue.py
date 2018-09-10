from html.parser import HTMLParser
import json
import os.path
from pathlib import Path
import re

import HTTPHandler # Make sure get() is available

class VueParser(HTMLParser):
	# https://www.w3.org/TR/2011/WD-html-markup-20110113/syntax.html#syntax-elements
	voidElements = {'area', 'base', 'br', 'col', 'command', 'embed', 'hr', 'img', 'input', 'keygen', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

	def __init__(self, path):
		super().__init__()
		self.stack = []
		self.locs = {}

		self.text = path.read_text()
		try:
			self.feed(self.text)
			self.close()
		except Exception as e:
			raise ValueError(f"Failed to parse {path}: {e}")

	def handle_starttag(self, tag, attrs):
		# print(f"start @{self.getpos()}: {tag}, {attrs}")
		if tag not in self.voidElements:
			# The offset is the beginning of the tag, but we want to start at the data inside the tag
			self.stack.append((tag, attrs, self.getOffset() + len(self.get_starttag_text())))

	def handle_endtag(self, tag):
		# print(f"end @{self.getpos()}: {tag}")
		startTag, attrs, off = self.stack.pop()
		if tag != startTag:
			endLine, endOff = self.getpos()
			raise ValueError(f"<{startTag}> closed by </{tag}> at {endLine}:{endOff}")
		if not self.stack:
			tag, attrs = self.tagMod(tag, attrs)
			if tag in self.locs:
				raise SyntaxError(f"Duplicate Vue SFC block: <{tag}>")
			self.locs[tag] = (attrs, off, self.getOffset())

	def handle_startendtag(self, tag, attrs):
		self.handle_starttag(tag, attrs)
		if tag not in self.voidElements:
			self.handle_endtag(tag)

	def getOffset(self):
		# Convert the line number/offset result from getpos() to a raw offset
		lineno, off = self.getpos()
		rtn = 0
		for _ in range(lineno - 1):
			rtn = self.text.find('\n', rtn) + 1
		return rtn + off

	def tagMod(self, tag, attrs):
		# Tags like <foo bar> are converted to <foo-bar>. <foo bar="baz"> is left alone.
		# This is used to facilitate custom blocks like <script vue>
		rest = {}
		for (lhs, rhs) in attrs:
			if rhs is None:
				tag += f"-{lhs}"
			else:
				rest[lhs] = rhs
		return tag, rest

	def getBlocks(self, validBlocks):
		rtn = {name: self.text[startOff:endOff] for name, (attrs ,startOff, endOff) in self.locs.items()}
		actualBlocks = set(rtn.keys())
		if not actualBlocks <= validBlocks:
			raise SyntaxError(f"Unexpected blocks: {', '.join(sorted(actualBlocks - validBlocks))}")

		for name in rtn:
			if (name == 'script' or name.startswith('script-')) and rtn[name].strip().startswith('export default '):
				rtn[name] = rtn[name].replace('export default ', '', 1)

		return rtn

class VueComponents:
	def __init__(self, rootDir, route = None):
		self.components = {}
		self.globalNames = []
		self.rootDir = Path(rootDir).resolve()

		thirdPartyJS, thirdPartyCSS = '', ''
		for pth in (self.rootDir / 'third-party').iterdir():
			_, ext = os.path.splitext(pth)
			if ext == '.js':
				thirdPartyJS += f"\n// {os.path.basename(pth)}\n\n{pth.read_text()}\n"
			elif ext == '.css':
				thirdPartyCSS += f"\n/* {os.path.basename(pth)} */\n\n{pth.read_text()}\n"
			else:
				raise ValueError(f"Unexpected third-party component file: {pth}")

		for pth in self.rootDir.iterdir():
			if pth.is_file():
				self.loadComponent(pth)

		# allowGuest isn't actually used in rorn, but it's set here for app usage
		@get(f"{route or rootDir}.js", allowGuest = True)
		def handler(handler, **components):
			print(thirdPartyJS)
			print('/' * 80)
			self.renderAllVia(list(components.keys()), self.renderJS)
			handler.contentType = 'text/javascript'
			handler.wrappers = False

		@get(f"{route or rootDir}.less", allowGuest = True)
		def handler(handler, **components):
			print(thirdPartyCSS)
			print('/' + '*' * 78 + '/')
			self.renderAllVia(list(components.keys()), self.renderStyle)
			handler.contentType = 'text/css'
			handler.wrappers = False

	def loadComponent(self, path):
		name, _ = os.path.splitext(os.path.basename(path))
		if name in self.components:
			raise ValueError(f"Duplicate Vue SFC component: {name}")
		# print(f"Loading Vue component: {name}")

		try:
			blocks = VueParser(path).getBlocks({'import', 'global', 'template', 'script', 'style'})
		except Exception as e:
			raise ValueError(f"Malformed view `{name}': {e}")

		# Don't think there's any use case for this
		if 'template' not in blocks:
			raise SyntaxError(f"No <template> block in Vue SFC component `{name}'")
		if 'global' in blocks and blocks['global'] != '':
			raise SyntaxError(f"Non-empty <global> block in Vue SFC component `{name}'")

		blocks['import'] = blocks['import'].split() if 'import' in blocks else []

		if 'global' in blocks:
			self.globalNames.append(name)
			del blocks['global']
		self.components[name] = blocks

	def __getitem__(self, item):
		if item not in self.components:
			raise ValueError(f"Unregistered component: {item}")
		return self.components[item]

	def renderAllVia(self, componentNames, renderer):
		processed = set()
		worklist = self.globalNames + componentNames
		while worklist:
			name = worklist.pop(0)
			if name in processed:
				continue
			processed.add(name)
			worklist += self[name]['import']
			renderer(name)

	def renderJS(self, name):
		component = self[name]
		# dedent doesn't work because the variables are multi-line
		print(f"""
(function() {{
	var componentInfo =
{component.get('script', '{}')}
	componentInfo.template = {json.dumps(component['template'])};
	Vue.component('{name}', componentInfo);
}})();
""")

	def renderStyle(self, name):
		component = self[name]
		if 'style' in component:
			print(component['style'])

class Views:
	def __init__(self, rootDir, route = None):
		self.rootDir = Path(rootDir).resolve()
		self.views = {}

		for pth in self.rootDir.iterdir():
			if pth.is_file():
				self.loadView(pth)

		# allowGuest isn't actually used in rorn, but it's set here for app usage
		@get(f"{route or rootDir}/(?P<viewName>[^/]+).js", allowGuest = True)
		def handler(handler, viewName):
			print(self[viewName].get('script', ''))
			handler.contentType = 'text/javascript'
			handler.wrappers = False

		@get(f"{route or rootDir}/(?P<viewName>[^/]+).less", allowGuest = True)
		def handler(handler, viewName):
			print(self[viewName].get('style', ''))
			handler.contentType = 'text/css'
			handler.wrappers = False

	def __getitem__(self, item):
		if item not in self.views:
			raise ValueError(f"Unregistered view: {item}")
		return self.views[item]

	def loadView(self, path):
		name, _ = os.path.splitext(os.path.basename(path))
		if name in self.views:
			raise ValueError(f"Duplicate view: {name}")

		try:
			blocks = VueParser(path).getBlocks({'components', 'view', 'script', 'style', 'script-vue'})
		except Exception as e:
			raise ValueError(f"Malformed view `{name}': {e}")

		# Don't think there's any use case for this
		if 'view' not in blocks:
			raise SyntaxError(f"No <view> block in view `{name}'")
		# 'view' is a strange name for the data; call it HTML instead
		blocks['html'] = blocks['view']
		del blocks['view']

		blocks['components'] = blocks['components'].split() if 'components' in blocks else []

		self.views[name] = blocks
