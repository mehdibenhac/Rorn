from pathlib import Path

from .utils import *

try:
	import pygments
	from pygments.lexers import PythonLexer
	from pygments.formatters import HtmlFormatter
	from pygments.styles.borland import BorlandStyle as LightStyle
	from pygments.styles.native import NativeStyle as DarkStyle
except ImportError:
	pygments = None

class IllegalFilenameError(RuntimeError): pass

def showCode(filename, line, around = None):
	path = Path(filename)
	if not path.is_absolute():
		path = Path(basePath()).resolve() / path
	validParents = [Path(basePath())] + [Path(p) for p in sys.path]
	if not set(path.parents) & set(validParents):
		raise IllegalFilenameError(f"File {path} not part of codebase or standard library")
	elif not path.is_file():
		raise IllegalFilenameError(f"Unknown file {path}")

	data = path.read_text()

	lines = highlightCode(data)
	if lines is None:
		return

	line = min(max(line, 1), len(lines))
	print("<table class=\"code_default dark\">")
	for i, text in enumerate(lines):
		if around and not line - around <= i + 1 <= line + around:
			continue
		if i + 1 == line:
			print("<tr class=\"selected_line\">")
		else:
			print("<tr>")
		print("<td class=\"icon\">&nbsp;</td>")
		print("<td class=\"p_linum\">%s</a></td>" % ('%3d' % (i + 1)).replace(' ', '&nbsp;'))
		print("<td class=\"code_line\">%s</td>" % text.replace('\t', ' ' * 4))
		print("</tr>")
	print("</table>")

def highlightCode(text):
	return None if pygments is None else pygments.highlight(text, PythonLexer(), HtmlFormatter(nowrap = True)).split('\n')

def showCodeCSS():
	print((Path(__file__).resolve().parent / 'syntax-highlighting.css').read_text())
	if pygments is not None:
		print(HtmlFormatter(style = LightStyle).get_style_defs('.code_default.light'))
		print(HtmlFormatter(style = DarkStyle).get_style_defs('.code_default.dark'))
