import json
import os.path
from pathlib import Path
import re

import HTTPHandler # Make sure get() is available

def vueLoader(path):
	# This is a super limited version of vue-loader
	# The file syntax should be close to standard, but the parsing is much more fragile

	blocks = {}

	wholeRE = re.compile("<([a-z]+) ?/>")
	startRE = re.compile("<([a-z]+)(?: [^>]*)*>")
	curBlock = None
	with open(path) as f:
		for line in f:
			if curBlock:
				if line.rstrip() == f"</{curBlock}>":
					curBlock = None
				else:
					blocks[curBlock] += line
				continue

			m = wholeRE.fullmatch(line.rstrip())
			if m:
				blocks[m.group(1)] = ''
				continue

			m = startRE.fullmatch(line.rstrip())
			if m:
				curBlock = m.group(1)
				if curBlock in blocks:
					raise SyntaxError(f"Duplicate Vue SFC block: <{curBlock}>")
				blocks[curBlock] = ''
				continue

			# Current discarding anything outside of a block, but should possibly be an error
			pass

	return blocks

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

		blocks = vueLoader(path)
		if not set(blocks.keys()) <= {'import', 'global', 'template', 'script', 'style'}:
			raise SyntaxError(f"Unexpected blocks in Vue SFC component: {name}")

		# Don't think there's any use case for this
		if 'template' not in blocks:
			raise SyntaxError(f"No <template> block in Vue SFC component: {name}")
		if 'global' in blocks and blocks['global'] != '':
			raise SyntaxError(f"Non-empty <global> block in Vue SFC component: {name}")

		if 'script' in blocks and blocks['script'].strip().startswith('export default '):
			blocks['script'] = blocks['script'].replace('export default ', '', 1)

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

		blocks = vueLoader(path)
		if not set(blocks.keys()) <= {'components', 'view', 'script', 'style'}:
			raise SyntaxError(f"Unexpected blocks in view: {name}")

		# Don't think there's any use case for this
		if 'view' not in blocks:
			raise SyntaxError(f"No <view> block in view: {name}")
		# 'view' is a strange name for the data; call it HTML instead
		blocks['html'] = blocks['view']
		del blocks['view']

		blocks['components'] = blocks['components'].split() if 'components' in blocks else []

		self.views[name] = blocks
