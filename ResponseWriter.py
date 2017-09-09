import sys
from _thread import get_ident

from .Lock import synchronized

class ResponseWriterManager:
	def __init__(self):
		self.writers = {}
		self.old = sys.stdout
		sys.stdout = self

	@synchronized('response-writer-manager')
	def add(self, writer):
		ident = get_ident()
		if ident not in self.writers:
			self.writers[ident] = []
		if writer not in self.writers[ident]:
			self.writers[ident].append(writer)

	@synchronized('response-writer-manager')
	def remove(self, writer):
		ident = get_ident()
		if writer in self.writers[ident]:
			self.writers[ident].remove(writer)
			if self.writers[ident] == []:
				del self.writers[ident]

	@synchronized('response-writer-manager')
	def write(self, data):
		ident = get_ident()
		if ident in self.writers:
			self.writers[ident][-1].write(data)
		else:
			self.old.write(data)

manager = ResponseWriterManager()

class ResponseWriter:
	def __init__(self, autoStart = True, storageType = str):
		if storageType not in (str, bytes):
			raise ValueError("Invalid storageType")
		self.storageType = storageType
		if autoStart:
			self.start()

	def write(self, data):
		if self.storageType is str and type(data) is bytes:
			data = data.decode('utf8')
		elif self.storageType is bytes and type(data) is str:
			data = data.encode('utf8')
		self.data += data

	def clear(self):
		self.data = self.storageType()

	def start(self):
		manager.add(self)
		self.clear()

	def done(self):
		manager.remove(self)
		return self.data
