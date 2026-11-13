"""A workspace is the folder that holds one player's data: game logs, built data, the dashboard file, the video record.

Any folder with an elevendash.json in it is a workspace; `elevendash init` makes one. The code never has to live there.
Logs hold the game's account tokens, so a workspace is private: share the dashboard file, never the folder.
"""
import json
import os

CONFIG = 'elevendash.json'


class NotAWorkspace(Exception):
    pass


class Workspace:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.config_path = os.path.join(self.root, CONFIG)
        self.logs = os.path.join(self.root, 'logs')
        self.build = os.path.join(self.root, 'build')
        self.site = os.path.join(self.root, 'site')
        self.videos = os.path.join(self.root, 'videos.json')

    def config(self):
        try:
            with open(self.config_path, encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def set(self, **values):
        c = self.config()
        c.update(values)
        with open(self.config_path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(c, f, indent=1)
            f.write('\n')


def find(explicit=None):
    """The workspace named by --dir, else by ELEVENDASH_HOME, else the current folder. Raises NotAWorkspace."""
    root = os.path.abspath(explicit or os.environ.get('ELEVENDASH_HOME') or os.getcwd())
    if not os.path.isfile(os.path.join(root, CONFIG)):
        raise NotAWorkspace(f'{root} is not an elevendash workspace (it has no {CONFIG}). Run "elevendash init" there, '
                            'or pass --dir, or set ELEVENDASH_HOME.')
    return Workspace(root)


def init(root, quest=None):
    ws = Workspace(root)
    os.makedirs(ws.logs, exist_ok=True)
    if not os.path.exists(ws.config_path):
        ws.set(version=1)
    if quest:
        ws.set(quest=quest)
    return ws
