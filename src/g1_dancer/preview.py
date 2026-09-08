"""Local, temporary, dry-run preview; never connects to robot hardware."""
import argparse
import tempfile
import webbrowser
from .cli import _components, _seed
from .config import Config
from .server import serve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=8788)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='g1-preview-') as directory:
        config = Config(data_dir=directory, listen_host='127.0.0.1', listen_port=args.port, dry_run=True)
        store, player = _components(config)
        _seed(store)
        url = f'http://127.0.0.1:{args.port}/?demo'
        print(f'Safe visual demo: {url}', flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        serve(config, store, player)


if __name__ == '__main__':
    main()
