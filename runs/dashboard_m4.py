import sys

from ca.dashboard import create_app


if __name__ == '__main__':
    port = int(sys.argv[1])
    app = create_app(preferred_runs=('onda-manha-kennedy', 'onda-tarde-kennedy'))
    app.run(host='127.0.0.1', port=port, debug=False, load_dotenv=False)
