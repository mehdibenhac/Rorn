from http.cookies import SimpleCookie
import time
import base64
import os
from .utils import md5, ucfirst
from datetime import datetime, timedelta
import pickle

from .Lock import synchronized

serializer = None

class Session(object):
	def __init__(self, key):
		self.key = key
		self.map = {}
		self.persistent = set() # Only keys in this set are saved to disk

	@synchronized('session')
	def keys(self):
		return list(self.map.keys())

	@synchronized('session')
	def values(self):
		return list(self.map.values())

	@synchronized('session')
	def __getitem__(self, k):
		return self.map[k] if k in self.map else None

	@synchronized('session')
	def __setitem__(self, k, v):
		self.map[k] = v
		serializer.save(self.key)

	@synchronized('session')
	def __delitem__(self, k):
		del self.map[k]
		serializer.save(self.key)

	@synchronized('session')
	def remember(self, *keys):
		self.persistent.update(keys)
		serializer.save(self.key)

	@synchronized('session')
	def __contains__(self, k):
		return k in self.map

	@synchronized('session')
	def __iter__(self):
		return self.map.__iter__()

	@synchronized('session')
	def __getstate__(self):
		return (self.key, {k: v for (k, v) in self.map.items() if k in self.persistent})

	@synchronized('session')
	def __setstate__(self, tpl):
		self.key, self.map = tpl
		self.persistent = set(self.map.keys())

	@staticmethod
	@synchronized('session')
	def determineKey(handler):
		if 'Cookie' in handler.headers:
			c = SimpleCookie()
			c.load(handler.headers['Cookie'])
			if 'session' in c:
				return c['session'].value
		return Session.generateKey()

	@staticmethod
	@synchronized('session')
	def generateKey():
		key = md5(os.urandom(128) + str(time.time()).encode('ascii'))[:-3].replace('/', '$')
		if key in Session.getIDs():
			return None
		return key

	@staticmethod
	@synchronized('session')
	def load(key):
		return serializer.get(key)

	@staticmethod
	@synchronized('session')
	def getIDs():
		return serializer.getIDs()

	@staticmethod
	@synchronized('session')
	def destroy(key):
		serializer.destroy(key)

class SessionSerializer:
	def __init__(self):
		try:
			with open('session', 'rb') as f:
				self.sessions = pickle.load(f)
		except Exception:
			self.sessions = {}

	def get(self, sessionID):
		if sessionID not in self.sessions:
			self.sessions[sessionID] = Session(sessionID)
			self.saveAll()
		return self.sessions[sessionID]

	def save(self, sessionID):
		self.saveAll()

	def getIDs(self):
		return list(self.sessions.keys())

	def destroy(self, sessionID):
		del self.sessions[sessionID]
		self.saveAll()

	# This is internal; not necessary for other implementations
	def saveAll(self):
		with open('session', 'wb') as f:
			pickle.dump(self.sessions, f)

def setSerializer(store):
	global serializer
	serializer = store

setSerializer(SessionSerializer()) # Default

def timestamp(days = 7):
	return (datetime.utcnow() + timedelta(days)).strftime("%a, %d-%b-%Y %H:%M:%S GMT")

def delay(handler, item):
	if 'delayed' not in handler.session:
		handler.session['delayed'] = []
	handler.session['delayed'].append(item)

def undelay(handler):
	if 'delayed' in handler.session:
		for item in handler.session['delayed']:
			print(item)
		del handler.session['delayed']
