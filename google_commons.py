from oauth2client import GOOGLE_REVOKE_URI
from oauth2client import GOOGLE_TOKEN_URI
from oauth2client import GOOGLE_TOKEN_INFO_URI
from iotmirror_commons.oauth2_tokens import CredentialsProvider

class GoogleCredentialsProvider(CredentialsProvider):
  def __init__(self, client_id, client_secret):
    super().__init__(client_id, client_secret, GOOGLE_TOKEN_URI, GOOGLE_REVOKE_URI,
                     GOOGLE_TOKEN_INFO_URI)
