import requests
from datetime import datetime
from bs4 import BeautifulSoup as bs
from itertools import chain
import json
import pymongo
import time
import pytz

start = time.time()

password = open("password", "r").read().strip()

class Scraper():

    client = pymongo.MongoClient("mongodb+srv://flask-app:" + password +"@cluster.menwf.mongodb.net/myFirstDatabase?retryWrites=true&w=majority")
    database = client["vodime"]
    connections = database["connections"]

    stations = json.load(open("data/final_data.json"))
    arriva_ids = json.load(open("data/arriva_stations.json"))

    def scrape_arriva(self, fromId, toId, date):
        params = {
                "departure_id": self.get_arriva_station_id(fromId),
                "departure": " ",
                "destination_id": self.get_arriva_station_id(toId),
                "destination": " ",
                "date": date.strftime("%d.%m.%Y")
                }

        response = requests.get("https://arriva.si/vozni-redi/?", params = params)
        soup = bs(response.text, features = "html.parser")

        for odhod in soup.select(".collapse.display-path"):
            if "connection-header" in odhod["class"]:
                continue
            data_odhod = json.loads(odhod["data-args"])

            yield {
                    "details_url": None,
                    "tickets_url": None,
                    "arrival": data_odhod["ROD_IPRI"],
                    "departure": data_odhod["ROD_IODH"],
                    "departure_station_name": self.get_arriva_station_name(fromId),
                    "destination_station_name": self.get_arriva_station_name(toId),
                    "duration": data_odhod["ROD_CAS"],
                    "online_ticket_avalible": False,
                    "url": response.url,
                    "route_name": data_odhod["RPR_NAZ"],
                    "length": data_odhod["ROD_KM"],
                    "price": data_odhod["VZCL_CEN"]
            }

    def scrape_aplj(self, fromId, toId, date):

        params = {
                "departure": self.get_aplj_station_name(fromId),
                "destination": self.get_aplj_station_name(toId),
                "date": date.strftime("%d.%m.%Y")
                }

        response = requests.get("https://www.ap-ljubljana.si/vozni-red/?", params = params)
        soup = bs(response.text, features = "html.parser")

        for odhod in soup.find_all("odhod"):
            if odhod["je-mednarodni"] == "True":
                continue

            details = bs(requests.get("https://www.ap-ljubljana.si/" + odhod["request-details-url"]).text, features="html.parser")
            details_list = list(filter(lambda x: x, details.text.strip().split("\n")))

            yield {
                    "details_url": odhod["request-details-url"],
                    "tickets_url": odhod.get("request-tickets-url"),
                    "arrival": odhod["cas-prihoda"],
                    "departure": odhod["cas-odhoda"],
                    "departure_station_name": odhod["naziv-odhoda"],
                    "destination_station_name": odhod["naziv-prihoda"],
                    "duration": (odhod["cas-voznje"].split(" ")[0]),
                    "online_ticket_avalible": odhod["nakup-mozen"],
                    "url": response.url,
                    "route_name": details_list[0][8:],
                    "agency": details_list[1],
                    "intermittent_stations": [([item[:-5], item[-5:]] if item[-5].isnumeric() else [item[:-4], item[-4:]]) for item in details_list[2:]]
            }

    def get_arriva_station_id(self, stationId):
        return self.arriva_ids[self.get_arriva_station_name(stationId)]

    def get_arriva_station_name(self, stationId):
        return self.stations[stationId]["arriva_name"][0]

    def get_aplj_station_name(self, stationId):
        return self.stations[stationId]["aplj_name"][0]

    def get_connection_data(self, fromId, toId, date):

        connection_from_database = self.get_connection_data_from_database(fromId, toId, date)

        if connection_from_database:
            return connection_from_database["connections"]

        data = list(chain(self.scrape_aplj(fromId, toId, date) , self.scrape_arriva(fromId, toId, date)))

        self.connections.insert_one({
            "fromId": fromId,
            "toId": toId,
            "date": date.strftime("%d:%m:%Y"),
            "connections": data,
            "timestamp": datetime.now(pytz.utc).timestamp()
        })

        return data


    def get_connection_data_from_database(self, fromId, toId, date):
        return self.connections.find_one({"fromId": fromId, "toId": toId, "date": date.strftime("%d:%m:%Y")})

    def connection_exists(self, fromId, toId, date):
        data = self.get_connection_data(fromId, toId, date)
        for connection in data:
            print(connection["departure"], date.strftime("%H:%M"))
            if connection["departure"] == date.strftime("%H:%M"):
                return connection

class Connector:

    scraper = Scraper()

    api_endpoint = "http://localhost:8080/otp/routers/default"

    def get_connections(self, params):

        response = requests.get(self.api_endpoint + "/plan", params = params)

        data = response.json()

        return self.check_response_data(data)

    def check_response_data(self, data):
        for itinerarie in data["plan"]["itineraries"]:
            for leg in itinerarie["legs"]:
                if leg["mode"] == "BUS":

                    datetime = datetime.fromtimestamp(leg["startTime"]/1000).astimezone(pytz.timezone("Europe/Ljubljana"))
                    fromId = leg["from"]["stopId"].split(":")[1]
                    toId = leg["to"]["stopId"].split(":")[1]

                    connection = self.scraper.connection_exists(fromId, toId, datetime)

                    if connection:
                        leg["checked"] = True
                        leg["connection_checked_data"] = connection
        return data

print("Processing time: ",time.time()-start)
