# Mock objects for running outside of Kodi
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3
    def log(self, msg, level=0): pass

class MockXBMCAddon:
    def __init__(self, id=None): self._id = id
    def getAddonInfo(self, key): return ""
    def getSetting(self, key): return ""
    def getLocalizedString(self, code): return f"STR_{code}"

class MockDialog:
    def input(self, heading, defaultt="", type=0, option=0): return "mock_input"
    def ok(self, heading, line1, line2=None, line3=None): pass

class MockListItem:
    def __init__(self, label=""): self.label = label
    def setProperty(self, key, value): pass
    def setArt(self, art): pass
    def setInfo(self, type, info): pass

class MockXBMCGUI:
    INPUT_PASSWORD = 1
    Dialog = MockDialog
    ListItem = MockListItem

xbmc = MockXBMC()
xbmcaddon = MockXBMCAddon()
xbmcgui = MockXBMCGUI()
