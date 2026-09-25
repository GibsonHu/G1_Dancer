"""Read-only discovery of installed UniStore apps. No playback API is exposed."""
import json
import threading
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


# Names currently shipped by UniStore on this robot. Keeping these local means
# the first render is instantaneous even when the robot has no internet route.
_OFFLINE_TRANSLATIONS = {
    "G1-韦伯斯特前空翻": "G1 Webster Front Flip",
    "比心": "Heart Gesture",
    "整活扭动机器人": "Fun Robot Twist",
    "抖音热门舞蹈": "Popular Douyin Dance",
    "螳螂拳": "Mantis Kung Fu",
    "咏春": "Wing Chun",
    "杰克逊": "Jackson Dance",
    "机械舞": "Mechanical Dance",
    "小城夏天元气舞": "Small Town Summer Dance",
}


def _has_chinese(value):
    return any("\u4e00" <= char <= "\u9fff" for char in value)


class ChineseToEnglish:
    """Small persisted translator for public dance names; never sends robot data."""
    def __init__(self, root):
        self.path = root / "translations.json"
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            self.cache = value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            self.cache = {}

    def translate(self, text, fallback_id):
        if not _has_chinese(text):
            return text
        result = self.cache.get(text) or _OFFLINE_TRANSLATIONS.get(text)
        if not result:
            try:
                query = urlencode({"client": "gtx", "sl": "zh-CN", "tl": "en", "dt": "t", "q": text})
                request = Request("https://translate.googleapis.com/translate_a/single?" + query,
                                  headers={"User-Agent": "G1-Dancer/1.0"})
                response = json.load(urlopen(request, timeout=2))
                result = "".join(part[0] for part in response[0] if part and part[0])
            except (OSError, ValueError, TypeError, IndexError):
                result = None
        # Never show untranslated Chinese in the English UI. A future refresh
        # can replace this safe fallback when translation is reachable.
        if not isinstance(result, str) or not result.strip() or _has_chinese(result):
            return f"Unitree action {fallback_id}"
        self.cache[text] = result.strip()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return self.cache[text]


class UniStoreCatalog:
    def __init__(self, root):
        self.path = root / "unistore_apps.json"
        self.translator = ChineseToEnglish(root)
        self.lock = threading.Lock()
        self.apps = []
        self.updated_at = None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            self.apps = self.decode(value["apps"])
            self.updated_at = value.get("updated_at")
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def decode(self, apps):
        if not isinstance(apps, list):
            raise ValueError("Invalid UniStore app list")
        result = []
        for app in apps:
            if not isinstance(app, dict) or app.get("install_status") != "installed":
                continue
            if not isinstance(app.get("id"), str) or not app["id"].isdigit():
                continue
            if not isinstance(app.get("name"), str):
                continue
            # Allowlist fields: never persist or return request tokens.
            item = {key: app[key] for key in (
                "id", "name", "version", "install_status", "running_status",
                "instance_id", "app_runtime", "category", "cover", "icon_url",
            ) if key in app}
            if _has_chinese(item["name"]):
                item["original_name"] = item["name"]
                item["name"] = self.translator.translate(item["name"], item["id"])
            for key in ("cover", "icon_url"):
                url = item.get(key)
                if not isinstance(url, str) or urlsplit(url).scheme != "https":
                    item.pop(key, None)
            # API 1005 with action_id "1" was captured from the official app.
            # It starts the app only; no non-Damp stop protocol is exposed.
            item["startable"] = bool(item.get("instance_id"))
            result.append(item)
        return result

    def discover(self, robot):
        with self.lock:
            error = None
            cached = True
            try:
                value = robot.get_unistore_apps()
                self.apps = self.decode(value["data"]["apps"])
                self.updated_at = datetime.now(timezone.utc).isoformat()
                cached = False
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(json.dumps({"apps": self.apps, "updated_at": self.updated_at}), encoding="utf-8")
                temporary.replace(self.path)
            except (RuntimeError, OSError, ValueError, KeyError, TypeError):
                error = "Could not refresh UniStore. Check the robot connection."
            return {"apps": list(self.apps), "cached": cached,
                    "updated_at": self.updated_at, "error": error}

    def get(self, app_id, robot):
        result = self.discover(robot)
        for app in result["apps"]:
            if app["id"] == app_id:
                return app
        raise KeyError(app_id)
