from random import randint

from ResponseWriter import ResponseWriter
from utils import *

class Box:
	def __init__(self, title, text = None, id = None, clr = 'black'):
		if text:
			self.title = title
			self.text = text
		else:
			self.title = None
			self.text = title
		self.id = id
		self.clr = clr

	def __str__(self):
		writer = ResponseWriter()
		print "<div",
		if self.id:
			print "id=\"%s\"" % self.id,
		print "class=\"box %s rounded\">" % self.clr
		if self.title:
			print "<div class=\"title\">%s</div>" % self.title
		print "<span class=\"boxBody\">"
		print self.text
		print "</span>"
		print "</div>"
		return writer.done()

getID = id
class AlertBox:
	def __init__(self, title, text = None, id = None, close = None, fixed = False):
		if text:
			self.title = title
			self.text = text
		else:
			self.title = None
			self.text = title

		self.id = id or "alertbox-%x-%x" % (getID(self), randint(268435456, 4294967295))
		self.close = 0 if close == True else close
		self.fixed = fixed

	def getClasses(self):
		return ['alert-message'] + (['fixed'] if self.fixed else [])

	def __str__(self):
		writer = ResponseWriter()

		if self.close:
			print "<script type=\"text/javascript\">"
			print "$(document).ready(function() {hidebox($('#%s'), %d);});" % (self.id, self.close)
			print "</script>"

		print "<div",
		if self.id:
			print "id=\"%s\"" % self.id,
		print "class=\"%s\">" % ' '.join(self.getClasses())
		if self.close != None:
			print "<span class=\"close\">x</span>"
		print "<span class=\"boxbody\">"
		if self.title:
			print "<strong>%s</strong>: " % self.title
		print self.text
		print "</span>"
		print "</div>"
		return writer.done()

class InfoBox(AlertBox):
	def __init__(self, *args, **kargs):
		AlertBox.__init__(self, *args, **kargs)

	def getClasses(self):
		return AlertBox.getClasses(self) + ['info']

class SuccessBox(AlertBox):
	def __init__(self, *args, **kargs):
		AlertBox.__init__(self, *args, **kargs)

	def getClasses(self):
		return AlertBox.getClasses(self) + ['success']

class WarningBox(AlertBox):
	def __init__(self, *args, **kargs):
		AlertBox.__init__(self, *args, **kargs)

	def getClasses(self):
		return AlertBox.getClasses(self) + ['warning']

class ErrorBox(AlertBox):
	def __init__(self, *args, **kargs):
		AlertBox.__init__(self, *args, **kargs)

	def getClasses(self):
		return AlertBox.getClasses(self) + ['error']

	@staticmethod
	def die(*args):
		print ErrorBox(*args)
		done()

##########################

class CollapsibleBox:
	def __init__(self, title, text, expanded = False, id = None):
		self.title = title
		self.text = text
		self.expanded = expanded
		self.id = id

	def __str__(self):
		writer = ResponseWriter()
		print "<div",
		if self.id:
			print "id=\"%s\"" % self.id,
		print "class=\"box rounded collapsible",
		if self.expanded:
			print "expanded",
		print "\">"
		if self.title:
			print "<div class=\"title\">%s</div>" % self.title
		print "<span class=\"boxBody\">"
		print self.text
		print "</span>"
		print "</div>"
		return writer.done()
