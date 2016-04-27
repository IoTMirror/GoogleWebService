import flask
import json
import os
import uuid
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.client import TokenRevokeError
from oauth2client.client import FlowExchangeError
from oauth2client.client import HttpAccessTokenRefreshError
from apiclient import discovery
import httplib2
import psycopg2
import psycopg2.extras
from iotmirror_commons.oauth2_tokens import OAuth2StatesDatabase
from iotmirror_commons.oauth2_tokens import AccessTokensDatabase
from iotmirror_commons.json_commons import ObjectJSONEncoder
from google_commons import GoogleCredentialsProvider

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

if __name__ == '__main__':
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port = port)
