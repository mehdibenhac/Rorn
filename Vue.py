import json
import os.path
from pathlib import Path
import re

import HTTPHandler # Make sure get() is available

class Vue:
	def __init__(self, rootDir, route = None):
		self.components = {}
		self.globalNames = []

		for pth in Path(rootDir).iterdir():
			self.loadComponent(pth)

		# allowGuest isn't actually used in rorn, but it's set here for app usage
		@get(f"{route or rootDir}.js", allowGuest = True)
		def handler(handler, **components):
			self.renderAllVia(list(components.keys()), self.renderJS)
			handler.contentType = 'text/javascript'
			handler.wrappers = False

		@get(f"{route or rootDir}.less", allowGuest = True)
		def handler(handler, **components):
			self.renderAllVia(list(components.keys()), self.renderStyle)
			handler.contentType = 'text/css'
			handler.wrappers = False

	def loadComponent(self, path):
		# This is a super limited version of vue-loader
		# The file syntax should be close to standard, but the parsing is much more fragile

		name, _ = os.path.splitext(os.path.basename(path))
		if name in self.components:
			raise ValueError(f"Duplicate Vue SFC component: {name}")
		# print(f"Loading Vue component: {name}")

		blocks = {k: None for k in ('import', 'template', 'script', 'style')}
		isGlobal = False

		startRE = re.compile("<(%s)(?: [^>]*)*>" % '|'.join(re.escape(k) for k in blocks))
		curBlock = None
		with open(path) as f:
			for line in f:
				if curBlock:
					if line.strip() == f"</{curBlock}>":
						curBlock = None
					else:
						blocks[curBlock] += line
					continue

				if line.strip() == '<global />':
					isGlobal = True

				m = startRE.fullmatch(line.strip())
				if m:
					curBlock = m.group(1)
					if blocks[curBlock] is not None:
						raise SyntaxError(f"Duplicate Vue SFC block: <{curBlock}>")
					blocks[curBlock] = ''
					continue

				# Current discarding anything outside of a block, but should possibly be an error
				pass

		# Don't think there's any use case for this
		if blocks['template'] is None:
			raise SyntaxError(f"No <template> block in Vue SFC component: {name}")

		if blocks['script'] and blocks['script'].strip().startswith('export default '):
			blocks['script'] = blocks['script'].replace('export default ', '', 1)

		blocks['import'] = blocks['import'].split() if blocks['import'] else []

		self.components[name] = blocks
		if isGlobal:
			self.globalNames.append(name)

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
{component['script'] or '{}'}
	componentInfo.template = {json.dumps(component['template'])};
	Vue.component('{name}', componentInfo);
}})();
""")

	def renderStyle(self, name):
		component = self[name]
		if component['style'] is None:
			return
		print(component['style'])
