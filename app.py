from flask import Flask, request
from connector import Connector

app = Flask(__name__)
c = Connector()

@app.route("/plan")
def index():
    return c.get_connections(dict(request.args))

if __name__ == "__main__":
    app.run(port="5091")
