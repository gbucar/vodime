import requests
from datetime import datetime
from bs4 import BeautifulSoup
from itertools import chain
import json
import pymongo
import time

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
        soup = BeautifulSoup(response.text, features = "html.parser")

        for odhod in soup.find_all("div", {"class": "connection"}):
            if "connection-header" in odhod["class"]:
                continue
            yield {
                    "details_url": None,
                    "tickets_url": None,
                    "arrival": odhod.find(class_="arrival").get_text().strip(),
                    "departure": odhod.find(class_="departure").get_text().strip(),
                    "departure_station_name": None,
                    "destination_station_name": None,
                    "duration": odhod.find(class_="travel-duration").get_text().strip(),
                    "online_ticket_avalible": None,
                    "url": response.url
            }

    def scrape_aplj(self, fromId, toId, date):

        params = {
                "departure": self.get_aplj_station_name(fromId),
                "destination": self.get_aplj_station_name(toId),
                "date": date.strftime("%d.%m.%Y")
                }

        response = requests.get("https://www.ap-ljubljana.si/vozni-red/?", params = params)
        soup = BeautifulSoup(response.text, features = "html.parser")

        for odhod in soup.find_all("odhod"):
            if odhod["je-mednarodni"] == "True":
                continue
            yield {
                    "details_url": odhod["request-details-url"],
                    "tickets_url": odhod.get("request-tickets-url"),
                    "arrival": odhod["cas-prihoda"],
                    "departure": odhod["cas-odhoda"],
                    "departure_station_name": odhod["naziv-odhoda"],
                    "destination_station_name": odhod["naziv-prihoda"],
                    "duration": (odhod["cas-voznje"].split(" ")[0]),
                    "online_ticket_avalible": odhod["nakup-mozen"],
                    "url": response.url
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
            "timestamp": datetime.now().timestamp()
        })

        return data


    def get_connection_data_from_database(self, fromId, toId, date):
        return self.connections.find_one({"fromId": fromId, "toId": toId, "date": date.strftime("%d:%m:%Y")})

    def connection_exists(self, fromId, toId, date):
        data = self.get_connection_data(fromId, toId, date)
        for connection in data:
            if connection["departure"] == date.strftime("%H:%M"):
                return connection 

class Connector:

    scraper = Scraper()

    api_endpoint = "http://localhost:8080/otp/routers/default"

    def get_connections(self, fromPlace, toPlace, date, time,
            arriveBy="", intermediatePlaces="", maxHours="", maxPreTransitTime="", maxTransfers="", maxWalkDistance="", minTransferTime="", bikeSpeed="", mode="", optimize="", pathComparator="",
            preferredAgencies="", preferredRoutes="", showIntermediateStops="", triangleSafetyFactor="", triangleSlopeFactor="", triangleTimeFactor="", unpreferredAgencies="", 
            unpreferredRoutes="", waitAtBeginningFactor="", waitReluctance="", walkReluctance="", walkSpeed="", wheelchair="", whiteListedAgencies="", whiteListedRoutes="", 
            startTransitStopId="", startTransitTripId=""):

        params = locals()
        params.pop("self")


        response = requests.get(self.api_endpoint + "/plan", params = params)

        data = response.json()

        return self.check_response_data(data)

    def check_response_data(self, data):
        for itinerarie in data["plan"]["itineraries"]:
            for leg in itinerarie["legs"]:
                if leg["mode"] == "BUS":
                    connection = self.scraper.connection_exists(leg["from"]["stopId"].split(":")[1], leg["to"]["stopId"].split(":")[1], datetime.fromtimestamp(leg["startTime"]/1000))
                    if connection: 
                        leg["checked"] = True
                        leg["connection_checked_data"] = connection
        return data
c = Connector()
print(c.get_connections("45.75806222125841,14.056676864624023", "46.09314451433808,14.676511287689209", "07:05:2022", "17:32"))
print(time.time()-start)
