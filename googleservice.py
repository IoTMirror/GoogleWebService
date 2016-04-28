import flask
import json
import os
import uuid
import random
import math
import dateutil.parser
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.client import TokenRevokeError
from oauth2client.client import FlowExchangeError
from oauth2client.client import HttpAccessTokenRefreshError
from apiclient import discovery
from apiclient.errors import HttpError
import httplib2
import psycopg2
import psycopg2.extras
from iotmirror_commons.oauth2_tokens import OAuth2StatesDatabase
from iotmirror_commons.oauth2_tokens import AccessTokensDatabase
from iotmirror_commons.json_commons import ObjectJSONEncoder
from google_commons import GoogleCredentialsProvider
from google_utils import TaskProvider
from google_utils import EmailMessageProvider

app = flask.Flask(__name__)

client_id = os.environ['GOOGLE_CLIENT_ID']
client_secret = os.environ['GOOGLE_CLIENT_SECRET']
scopes = os.environ['GOOGLE_SCOPES']
dburl = os.environ['DATABASE_URL']
callback_url = os.environ['GOOGLE_CALLBACK_URL']
oauth2_states_table = "google_oauth2_states"
access_tokens_table = "google_access_tokens"
o2sdb = OAuth2StatesDatabase(dburl, oauth2_states_table)
atdb = AccessTokensDatabase(dburl, access_tokens_table)
credentials_provider = GoogleCredentialsProvider(client_id, client_secret)

#starts signin process for given user
@app.route('/signin/<user_id>', methods=['GET'])
def signinUser(user_id):
  flow = OAuth2WebServerFlow(client_id = client_id, client_secret = client_secret,
                             scope = scopes, redirect_uri = callback_url)
  flow.params["state"] = str(uuid.uuid4())
  flow.params['access_type'] = 'offline'
  o2sdb.insertState(flow.params["state"],user_id)
  url = flow.step1_get_authorize_url()
  return flask.redirect(url)

#exchanges request token for access tokens
@app.route('/signin', methods=['GET'])
def signinComplete():
  state = flask.request.args.get('state', None)
  if state is None:
    return ("", 400)
  error = flask.request.args.get('error', None)
  code = flask.request.args.get('code', None)
  if code is None:
    o2sdb.deleteState(state)
    return ""
  state_data = o2sdb.getState(state)
  o2sdb.deleteState(state)
  if state_data is None:
    return ("", 404)
  
  flow = OAuth2WebServerFlow(client_id = client_id, client_secret = client_secret,
                             scope = scopes, redirect_uri = callback_url)
  credentials = None
  try:
    credentials = flow.step2_exchange(code)
  except FlowExchangeError:
    return ("", 401)
  
  try:
    atdb.insertUserTokens(state_data["user_id"], credentials.access_token, credentials.refresh_token)
  except psycopg2.IntegrityError:
    if credentials.refresh_token is None:
      atdb.updateUserAccessToken(state_data["user_id"], credentials.access_token)
    else:
      atdb.updateUserTokens(state_data["user_id"], credentials.access_token, credentials.refresh_token)
  
  return ""

#revokes user access tokens from using app and deletes them from db
@app.route('/signout/<user_id>', methods=['DELETE'])
def signout(user_id):
  tokens = atdb.getUserTokens(user_id)
  if tokens is None:
    return ("", 404)
  credentials = credentials_provider.getCredentials(tokens["access_token"],tokens["refresh_token"])
  http = credentials.authorize(httplib2.Http())
  try:
    credentials.revoke(http)
  except TokenRevokeError:
    pass
  finally:
    atdb.deleteUserTokens(user_id)
  return ""

#revokes user access tokens from using app and deletes them from db
@app.route('/users/<user_id>/access_tokens', methods=['DELETE'])
def delete_user_access_tokens(user_id):
  return signout(user_id)

#deletes user oauth2 states from db
@app.route('/users/<user_id>/oauth2_states', methods=['DELETE'])
def delete_user_oauth2_states(user_id):
  o2sdb.deleteUserStates(user_id)
  return ""

#returns info about user specified by user_id
@app.route('/users/<user_id>', methods=['GET'])
def user_info(user_id):
  tokens = atdb.getUserTokens(user_id)
  if tokens is None:
    return ("", 404)
  credentials = credentials_provider.getCredentials(tokens["access_token"],tokens["refresh_token"])
  http = credentials.authorize(httplib2.Http())
  service = discovery.build('oauth2', 'v2', http = http)
  try:
    result = service.userinfo().get().execute()
    return json.dumps({"name" : result["name"],
                       "id" : result["id"],
                       "email" : result["email"]
                      },
                      cls = ObjectJSONEncoder
                     )
  except HttpAccessTokenRefreshError:  
    return ("",401)
  except HttpError as error:
    if error.resp.status == 403:
      return ("",429)
    raise

#returns tasks for user specified by user_id
@app.route('/users/<user_id>/tasks', methods=['GET'])
def user_tasks(user_id):
  max_tasks = 10
  tokens = atdb.getUserTokens(user_id)
  if tokens is None:
    return ("",404)
  credentials = credentials_provider.getCredentials(tokens["access_token"],tokens["refresh_token"])
  http = credentials.authorize(httplib2.Http())
  service = discovery.build('tasks', 'v1', http = http)
  task_provider = TaskProvider(service)
  try:
    tasks = task_provider.get_all_tasks(tasklist_info = True)
    tasks_separated = {
        "timed" : [x for x in tasks if x.get("due",None) is not None],
        "rest" : [x for x in tasks if x.get("due",None) is None]
      }
    tasks_separated["timed"].sort(key=lambda x: dateutil.parser.parse(x["due"]))
    random.shuffle(tasks_separated["rest"])
    timed_count = len(tasks_separated["timed"])
    rest_count = len(tasks_separated["rest"])
    timed_count_new = int(math.floor(min(max(max_tasks/2,max_tasks - rest_count),timed_count)))
    rest_count_new = int(math.floor(min(max_tasks-timed_count_new,rest_count)))
    tasks_separated["timed"] = (tasks_separated["timed"])[:timed_count_new]
    tasks_separated["rest"] = (tasks_separated["rest"])[:rest_count_new]
    return json.dumps(tasks_separated, cls = ObjectJSONEncoder)
  except HttpAccessTokenRefreshError:
    return ("",401)
  except HttpError as error:
    if error.resp.status == 403:
      return ("",429)
    raise

@app.route('/users/<user_id>/emails/inbox', methods=["GET"])
def user_email_inbox(user_id):
  max_messages = 10
  tokens = atdb.getUserTokens(user_id)
  if tokens is None:
    return ("",404)
  credentials = credentials_provider.getCredentials(tokens["access_token"],tokens["refresh_token"])
  http = credentials.authorize(httplib2.Http())
  service = discovery.build('gmail', 'v1', http = http)
  em_provider = EmailMessageProvider(service)
  try:
    messages = em_provider.get_inbox_messages_list(max_messages)
    return json.dumps(messages, cls = ObjectJSONEncoder)
  except HttpAccessTokenRefreshError:
    return ("",401)
  except HttpError as error:
    if error.resp.status == 403:
      return ("",429)
    raise

if __name__ == '__main__':
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port = port)
