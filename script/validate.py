#!/usr/bin/env python3
"""
Validate script for approving crackmes/solutions.
Moves the file from tmp/ to static/, zips it with password, and sends approval notification.
"""
import sys
import os
import datetime
from subprocess import call
from pymongo import MongoClient

# Determine base path from script location
# Script is in: <project>/scripts/validate.py
# Base path is: <project>/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
TMP_DIR = os.path.join(BASE_DIR, 'tmp')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

if len(sys.argv) < 3:
    print("Usage: python validate.py <crackme|solution> <file_loc>")
    sys.exit(1)

type_object = sys.argv[1]
file_loc = sys.argv[2]
[username, hexid, filename] = file_loc.split('+++')
send_notif = True

client = MongoClient('127.0.0.1')
db = client.crackmesone

if type_object == "crackme":
    file_path = os.path.join(TMP_DIR, 'crackme', file_loc)
    collection = db.crackme
elif type_object == "solution":
    file_path = os.path.join(TMP_DIR, 'solution', file_loc)
    collection = db.solution
else:
    print("[-] I don't understand the type")
    sys.exit(1)

db_object = collection.find_one({'hexid': hexid})

if db_object is None:
    print("not found in db")
    sys.exit(0)

print("[+] found in database !")
print(db_object)
print("[+] file set to visible")
collection.update_one({'hexid': hexid}, {'$set': {'visible': True}})

# Move file to current directory temporarily for zipping
temp_filename = os.path.join(os.getcwd(), filename)
call(["mv", file_path, temp_filename])
print("[+] mv " + file_path + " " + temp_filename)

# Create zip with password in static directory
zip_output = os.path.join(STATIC_DIR, type_object, hexid)
call(["zip", "-j", "--password", "crackmes.one", zip_output, temp_filename])
print("[+] zip -j --password crackmes.one " + zip_output + " " + temp_filename)

# Clean up temp file
if os.path.exists(temp_filename):
    os.remove(temp_filename)
    print("[+] rm " + temp_filename)

if send_notif:
    print("[+] Sending " + type_object + " approval notification!")
    notif_coll = db.notifications
    author_name = db_object["author"]
    if type_object == "solution":
        crackme_obj = db.crackme.find_one({'_id': db_object["crackmeid"]})
        ins_id = notif_coll.insert_one({
            "user": author_name,
            "time": datetime.datetime.now(datetime.timezone.utc),
            "seen": False,
            "text": "Your solution for '" + crackme_obj["name"] + "' has been accepted!"
        }).inserted_id
        # Set HexId here too for this case
        notif_coll.find_one_and_update({'_id': ins_id}, {'$set': {'hexid': str(ins_id)}})
        # Notify crackme author about new solution
        ins_id = notif_coll.insert_one({
            "user": crackme_obj["author"],
            "time": datetime.datetime.now(datetime.timezone.utc),
            "seen": False,
            "text": "A new solution for your crackme '" + crackme_obj["name"] + "' has been submitted by: " + author_name
        }).inserted_id
    elif type_object == "crackme":
        ins_id = notif_coll.insert_one({
            "user": author_name,
            "time": datetime.datetime.now(datetime.timezone.utc),
            "seen": False,
            "text": "Your crackme '" + db_object["name"] + "' has been accepted!"
        }).inserted_id
    # Set HexId here
    notif_coll.find_one_and_update({'_id': ins_id}, {'$set': {'hexid': str(ins_id)}})
