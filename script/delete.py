#!/usr/bin/env python3
"""
Delete script for rejecting crackmes/solutions.
Removes the file from tmp/ and sends a rejection notification.
"""
import sys
import os
import datetime
from subprocess import call
from pymongo import MongoClient

# Determine base path from script location
# Script is in: <project>/scripts/delete.py
# Base path is: <project>/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
TMP_DIR = os.path.join(BASE_DIR, 'tmp')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

if len(sys.argv) < 3:
    print("Usage: python delete.py <crackme|solution> <file_loc> [reject_reason]")
    sys.exit(1)

type_object = sys.argv[1]
file_loc = sys.argv[2]

[username, hexid, filename] = file_loc.split('+++')
send_notif = True
rej_reason = None
if send_notif and len(sys.argv) >= 4:
    rej_reason = sys.argv[3]

client = MongoClient('127.0.0.1')
db = client.crackmesone

if type_object == "crackme":
    file_path = os.path.join(TMP_DIR, 'crackme', file_loc)
    collection = db.crackme
    rating_diff = db.rating_difficulty
    rating_qual = db.rating_quality
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

collection.delete_one({'hexid': hexid})
print("[+] file deleted in db")

if type_object == "crackme":
    rating_diff.delete_many({"crackmehexid": hexid})
    rating_qual.delete_many({"crackmehexid": hexid})

if os.path.exists(file_path):
    os.remove(file_path)
    print("[+] rm " + file_path)
else:
    print("[!] File not found: " + file_path)

if send_notif:
    print("[+] Sending " + type_object + " rejection notification!")
    notif_coll = db.notifications
    users_coll = db.user
    author_name = db_object["author"]
    if type_object == "solution":
        crackme_obj = db.crackme.find_one({'_id': db_object["crackmeid"]})
        notif_text = "Your solution for '" + crackme_obj["name"] + "' has been rejected!"
        if rej_reason is not None:
            notif_text += " Reason: " + rej_reason
        ins_id = notif_coll.insert_one({
            "user": author_name,
            "time": datetime.datetime.now(datetime.timezone.utc),
            "seen": False,
            "text": notif_text
        }).inserted_id
    elif type_object == "crackme":
        notif_text = "Your crackme '" + db_object["name"] + "' has been rejected!"
        if rej_reason is not None:
            notif_text += " Reason: " + rej_reason
        ins_id = notif_coll.insert_one({
            "user": author_name,
            "time": datetime.datetime.now(datetime.timezone.utc),
            "seen": False,
            "text": notif_text
        }).inserted_id
    # Set HexId here
    notif_coll.find_one_and_update({'_id': ins_id}, {'$set': {'hexid': str(ins_id)}})
    users_coll.update_one({'name': author_name}, {'$inc': {'unread_notifications': 1}})
