from flask import Flask, request, Response, abort
import json

app = Flask(__name__)
HOST = 'localhost'
PORT = '18443'


@app.route('/', methods=['POST'])
def process_request():
    request_data = request.get_json()
    method = request_data.get('method')

    if method == "help":
        pass
    elif method == "getblockcount":
        pass
    elif method == "getblock":
        pass
    elif method == "getblockhash":
        pass
    elif method == "getrawtransaction":
        pass
    elif method == "decoderawtransaction":
        pass
    else:
        return abort(500, "Unsupported method")

    response = {"id": 0, "result": 0, "error": None}

    return Response(json.dumps(response), status=200, mimetype='application/json')


if __name__ == '__main__':
    app.run(host=HOST, port=PORT)