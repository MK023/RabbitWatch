#!/usr/bin/env python3
import yaml
from pymongo import MongoClient

CONFIG_PATH = "config_consumer.yaml"

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

mongo_conf = config["mongodb"]

MONGO_URI = mongo_conf["uri"]
DATABASE = mongo_conf["database"]
COLLECTIONS = [
    mongo_conf.get("collection_info", "metrics"),
    mongo_conf.get("collection_warning", "alerts")
]

client = MongoClient(MONGO_URI)
db = client[DATABASE]

for collection in COLLECTIONS:
    db[collection].create_index("timestamp", expireAfterSeconds=60*60*24*7)
    print(f"Creato indice TTL su '{collection}' per il campo 'timestamp' (7 giorni)")

print("Operazione completata.")