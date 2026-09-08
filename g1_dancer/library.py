"""Shared song titles and artwork, independent of robot routine definitions."""
import hashlib
import json
import threading
import uuid
from pathlib import Path


class Library:
    def __init__(self, root):
        self.root = root / 'library'
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def metadata(self, routine):
        path = self.root / (routine.id + '.json')
        with self.lock:
            return json.loads(path.read_text()) if path.exists() else {}

    def update(self, routine, **values):
        path = self.root / (routine.id + '.json')
        with self.lock:
            data = json.loads(path.read_text()) if path.exists() else {}
            data.update(values)
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(data))
            temp.replace(path)

    def public(self, routine):
        result = routine.public_dict()
        meta = self.metadata(routine)
        result['song_title'] = meta.get('song_title', Path(routine.audio).stem if routine.audio else '')
        result['artwork_url'] = '/api/routines/' + routine.id + '/artwork?v=' + str(meta.get('revision', '0'))
        return result

    def artwork(self, routine):
        meta = self.metadata(routine)
        if meta.get('artwork'):
            return (self.root / meta['artwork']).read_bytes(), meta['mime']
        hue = int(hashlib.sha256(routine.id.encode()).hexdigest()[:6], 16) % 360
        # Original vector covers stay sharp at every tile size, without online art services.
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">
        <defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="hsl({hue},70%,34%)"/><stop offset="1" stop-color="hsl({(hue+70)%360},80%,12%)"/></linearGradient></defs>
        <path fill="url(#g)" d="M0 0h600v600H0z"/>
        <g fill="none" stroke="hsl({(hue+40)%360},85%,77%)" stroke-width="28" opacity=".8">
        <ellipse cx="300" cy="300" rx="210" ry="82" transform="rotate(-35 300 300)"/>
        <ellipse cx="300" cy="300" rx="210" ry="82" transform="rotate(25 300 300)"/>
        <ellipse cx="300" cy="300" rx="210" ry="82" transform="rotate(85 300 300)"/></g>
        <circle cx="300" cy="300" r="32" fill="#efffea"/>
        <text x="36" y="554" font-family="sans-serif" font-size="18" fill="white" letter-spacing="5">G1 / SESSIONS</text></svg>'''
        return svg.encode(), 'image/svg+xml'

    def save_artwork(self, routine, data):
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            mime, ext = 'image/png', '.png'
        elif data.startswith(b'\xff\xd8\xff'):
            mime, ext = 'image/jpeg', '.jpg'
        else:
            raise ValueError('Choose a PNG or JPEG image')
        name = routine.id + '-' + uuid.uuid4().hex + ext
        (self.root / name).write_bytes(data)
        self.update(routine, artwork=name, mime=mime, revision=uuid.uuid4().hex)
