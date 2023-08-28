from urllib.request import urlopen
import json
from os import makedirs as os_makedirs, remove
from os.path import join as os_path_join, isfile, exists

from requests import get, exceptions

from _thread import start_new_thread

from skin import findSkinScreen

from Components.ActionMap import ActionMap
from Components.config import config, configfile, ConfigSubsection, ConfigSelection, ConfigText, getConfigListEntry
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Components.SystemInfo import SystemInfo

from Plugins.Plugin import PluginDescriptor

from Screens.Screen import Screen

from Tools.BoundFunction import boundFunction
from Tools.Directories import fileExists, resolveFilename, SCOPE_CONFIG, SCOPE_SKIN
from Tools.LoadPixmap import LoadPixmap


config.plugins.remotecontrolselection = ConfigSubsection()
config.plugins.remotecontrolselection.remote = ConfigText(default="", fixed_size=False)

data_path = "https://api.github.com/repos/oe-mirrors/branding-module/contents/BoxBranding/remotes"
download_path = "https://raw.githubusercontent.com/oe-mirrors/branding-module/master/BoxBranding/remotes"

tempDir = "/var/volatile/tmp/RemoteControlSelection"

def setRCFile(force=False):
	if not force and (not config.plugins.remotecontrolselection.remote.value or SystemInfo["rc_model"] == config.plugins.remotecontrolselection.remote.value):
		return
	SystemInfo["RCImage"] = resolveFilename(SCOPE_CONFIG, os_path_join("RemoteControlSelection", "rc.png"))
	SystemInfo["RCMapping"] = resolveFilename(SCOPE_CONFIG, os_path_join("RemoteControlSelection", "rcpositions.xml"))
	if not (isfile(SystemInfo["RCImage"]) and isfile(SystemInfo["RCMapping"])):
		SystemInfo["RCImage"] = resolveFilename(SCOPE_SKIN, os_path_join("rc_models", SystemInfo["rc_model"], "rc.png"))
		SystemInfo["RCMapping"] = resolveFilename(SCOPE_SKIN, os_path_join("rc_models", SystemInfo["rc_model"], "rcpositions.xml"))
	if not (isfile(SystemInfo["RCImage"]) and isfile(SystemInfo["RCMapping"])):
		SystemInfo["rc_default"] = True
	from Screens.Rc import RcPositions
	RcPositions.rc = None
	
setRCFile()  # update on initial load


def threadDownloadPage(link, file, success, fail=None):
	link = link.encode('ascii', 'xmlcharrefreplace').decode().replace(' ', '%20').replace('\n', '')
	try:
		response = get(link)
		response.raise_for_status()
		with open(file, "wb") as f:
			f.write(response.content)
		success(file)
	except exceptions.RequestException as error:
		if fail is not None:
			fail(error)


class RemoteControlSelection(ConfigListScreen, Screen):
	def __init__(self, session):
		self.config = config.plugins.remotecontrolselection
		Screen.__init__(self, session)
		self.title = _("Remote control selection")
		self.skinName = [self.__class__.__name__, "Setup"]
		self.skinAvailable = findSkinScreen(self.skinName[0])
		self["description"] = Label("")
		ConfigListScreen.__init__(self, [], on_change=self.updateImage, fullUI=True)
		self["rc"] = Pixmap()
		self["key_blue"] = StaticText()
		self["actions"] = ActionMap(["ColorActions"],
		{
			"blue": self.keyBlue,
		}, -2)
		self.onLayoutFinish.append(self.populate)
		
	def populate(self):
		self.getRemotes()
		if names := list(self.remotes.keys()):
			default = self.config.remote.value if self.config.remote.value in names else (SystemInfo["rc_model"] if SystemInfo["rc_model"] in names else name[0])
			self.remote = ConfigSelection(default=default, choices=names)
			self["config"].list = [getConfigListEntry(_("Remote"), self.remote, _("Choose the remote you want to use."))]
			self.updateImage()
		
	def fetchJson(self, path):
		try:
			return json.load(urlopen(path))
		except:
			import traceback
			traceback.print_exc()
		return []
	
	def getRemotes(self):
		self.remotes = {}
		for item in self.fetchJson(data_path):
			if item.get("type") == "dir":
				name = item.get("name")
				url = item.get("url")
				if name and url:
					self.remotes[name] = url

	def updateImage(self):
		self["key_blue"].text = _("Reset to default") if SystemInfo["rc_model"] != self.remote.value else ""
		if self.skinAvailable:
			os_makedirs(os_path_join(tempDir, self.remote.value), exist_ok=True)
			if not fileExists(filePath := os_path_join(tempDir, self.remote.value, "rc.png")):
				urlPath = os_path_join(download_path, self.remote.value, "rc.png")
				start_new_thread(threadDownloadPage, (urlPath, filePath, boundFunction(self.showImage, filePath), self.dataError))
			else:
				self.showImage(filePath)
		
			
	def showImage(self, image, *args, **kwargs):
		rc = LoadPixmap(image)
		if rc:
			self["rc"].instance.setPixmap(rc)

	def dataError(self, error):
		print("[RemoteControlSelection] Error: %s" % error)

	def fetchUrl(self, url):
		try:
			response = urlopen(url)
			return response.read()
		except:
			import traceback
			traceback.print_exc()
		return ""
			
	def keySave(self):
		confPath = resolveFilename(SCOPE_CONFIG)
		os_makedirs(os_path_join(confPath, "RemoteControlSelection"), exist_ok=True)
		if exists(rc_png := os_path_join(confPath, "RemoteControlSelection", "rc.png")):
			remove(rc_png)
		if exists(rcpositions := os_path_join(confPath, "RemoteControlSelection", "rcpositions.xml")):
			remove(rcpositions)
		if SystemInfo["rc_model"] != self.remote.value:
			url = self.remotes[self.remote.value]
			imageData = ""
			xmlData = ""
			for item in self.fetchJson(url):
				if item.get("name") == "rc.png":
					imageData = item
				elif item.get("name") == "rcpositions.xml":
					xmlData = item
				if imageData and xmlData:
					break
			os_makedirs(os_path_join(tempDir, self.remote.value), exist_ok=True)
			if not fileExists(filePath := os_path_join(tempDir, self.remote.value, "rc.png")):
				urlPath = os_path_join(download_path, self.remote.value, "rc.png")
				image = self.fetchUrl(urlPath)
			else:
				image = open(filePath, "rb").read()
			xmlPath = os_path_join(download_path, self.remote.value, "rcpositions.xml")
			xml = self.fetchUrl(xmlPath)
			if image and imageData and imageData.get("size") == len(image) and xml and xmlData and xmlData.get("size") == len(xml):
				open(rc_png, "wb").write(image)
				open(rcpositions, "wb").write(xml)
			self.config.remote.value = self.remote.value
		else:
			self.config.remote.value = ""
		self.config.remote.save()
		configfile.save()
		setRCFile(force=True)
		self.close()
			
	def keyCancel(self):
		self.close()

	def keyBlue(self):
		self.remote.value = SystemInfo["rc_model"]
		self.keySave()
				
			
def main(session, **kwargs):
	session.open(RemoteControlSelection)

def fromMenu(menuid, **kwargs):
	return [(_("Remote control selection"), main, "remotecontrolselection", 49)] if menuid == "system" else []
	

def Plugins(**kwargs):
	return [PluginDescriptor(name=_("Remote control selection"), where=PluginDescriptor.WHERE_MENU, needsRestart=False, fnc=fromMenu)]
#	return [PluginDescriptor(name=_("Remote control selection"), description=_("Select any remote from oe-mirrors branding module"), where=PluginDescriptor.WHERE_PLUGINMENU, fnc=main)]
