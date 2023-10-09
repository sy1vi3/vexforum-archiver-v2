import requests
import json
import random
import re
import time
import os
import datetime
import constants

db_user = os.environ['VF_DB_USER']
db_password = os.environ['VF_DB_PASS']
db_host = os.environ['VF_DB_HOST']
db_port = os.environ['VF_DB_PORT']
vf_pass = os.environ['VF_PASS']
vf_user = os.environ['VF_USER']
bot_token = os.environ['VF_BOT_TOKEN']
logs_webhook = os.environ['VF_LOGS_WEBHOOK']
login_url = f"https://vexforum.com/login?username={vf_user}&password={vf_pass}&redirect=https%3A%2F%2Fwww.vexforum.com%2F"
session_url = f"https://www.vexforum.com/session?login={vf_user}&password={vf_pass}"

def like_post(guid):
    headers = {
        "accept": "application/json"
    }
    s = requests.Session()
    r = s.post(login_url)
    r = s.get('https://www.vexforum.com/session/csrf', headers=headers).json()
    token = r['csrf']
    csrf_headers = {
        "x-csrf-token": token,
        "accept": "application/json"
    }
    r = s.post(session_url, headers=csrf_headers)
    r = s.post(f'https://www.vexforum.com/post_actions?id={guid}&post_action_type_id=2&flag_topic=false', headers=csrf_headers)
    return r.status_code

def timestamp_log():
    time_now = datetime.datetime.now()
    return f"{time_now.month}/{time_now.day}/{time_now.year} {time_now.hour}:{time_now.minute}"

async def post_analysis(post, trust_level, links):
    if post.author in constants.users_to_like:
        await like_post(post.guid)