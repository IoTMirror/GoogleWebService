from datetime import datetime
from datetime import timezone
import dateutil.parser

class TaskProvider(object):
  def __init__(self,service):
    self.service = service

  def get_all_tasks(self, tasks_with_id = False, tasklist_info = False, tasklists_with_id = False):
    tasks = []
    tasklists = self.get_tasklists()
    for tasklist in tasklists:
      tasks_from_list = self.get_tasks_from_list(tasklist["id"], tasks_with_id)
      if tasklist_info is True:
        self.add_tasklist_info_to_tasks(tasks_from_list,tasklist, tasklists_with_id)
      tasks.extend(tasks_from_list)
    return tasks

  def get_tasklists(self, include_id = True):
    tasklists = []
    pagetoken = None
    while True:
      result = None
      if pagetoken is None:
        result = self.service.tasklists().list().execute()
      else:
        result = self.service.tasklists().list(pageToken = pagetoken).execute()
      for tasklist in result.get("items", []):
        tasklists.append(self.extract_tasklist(tasklist, include_id))
      pagetoken = result.get("nextPageToken",None)
      if pagetoken is None:
        break
    return tasklists

  def extract_tasklist(self, tasklist, include_id = True):
    new_tasklist = {}
    new_tasklist["title"] = tasklist["title"]
    if include_id is True:
      new_tasklist["id"] = tasklist["id"]
    return new_tasklist

  def get_tasks_from_list(self, tasklist_id, include_id = False):
    tasks = []
    pagetoken = None
    while True:
      result = None
      if pagetoken is None:
        result = self.service.tasks().list(tasklist = tasklist_id, showCompleted = False).execute()
      else:
        result = self.service.tasks().list(tasklist = tasklist_id, showCompleted = False, pagetoken = tasks_pagetoken).execute()
      for task in result.get("items",[]):
        tasks.append(self.extract_task(task, include_id))
      pagetoken = result.get("nextPageToken",None)
      if pagetoken is None:
        break
    return tasks

  def extract_task(self, task, include_id = False):
    new_task = {}
    new_task["title"] = task["title"]
    if task.get("due",None) is not None:
      new_task["due"] = task["due"]
    if include_id is True:
      new_task["id"] = task["id"]
    return new_task

  def add_tasklist_info_to_tasks(self, tasks, tasklist, include_id = False):
    for task in tasks:
      self.add_tasklist_info_to_task(task, tasklist, include_id)

  def add_tasklist_info_to_task(self, task, tasklist, include_id = False):
    task["tasklist_info"] = self.extract_tasklist(tasklist, include_id)

class EmailMessageProvider(object):
  def __init__(self,service):
    self.service = service

  def get_inbox_messages_list(self, max_messages = None):
    messages = []
    pagetoken = None
    collected_messages = 0
    while max_messages is None or collected_messages < max_messages:
      messages_list_info = None
      if pagetoken is None:
        messages_list_info = self.service.users().messages().list(
            userId = "me", labelIds = ["INBOX","UNREAD"], maxResults = max_messages
          ).execute()
      else:
        messages_list_info = self.service.users().messages().list(
            userId = "me", labelIds = ["INBOX","UNREAD"], pageToken = pagetoken,
            maxResults = max_messages
          ).execute()
      for message_minimal in messages_list_info.get("messages",[]):
        message_metadata = self.get_message_metadata(message_minimal["id"])
        messages.append(self.extract_message_info(message_metadata))
        collected_messages += 1
        if max_messages is not None and collected_messages >= max_messages:
          break
      pagetoken = messages_list_info.get("nextPageToken",None)
      if pagetoken is None:
        break
    return messages

  def get_message_metadata(self,message_id):
    return self.service.users().messages().get(
        userId = "me", id = message_id, format = "metadata",
        metadataHeaders = ["From", "Subject", "Date", "To"]
      ).execute()

  def extract_message_info(self, message):
    new_message = {}
    for header in message["payload"]["headers"]:
      new_message[header["name"].lower()] = header["value"]
    return new_message

class EventProvider(object):
  def __init__(self, service):
    self.service = service

  def get_all_events(self, max_events = None, calendar_info = False, calendars_with_id = False):
    events = []
    for calendar in self.get_calendars():
      events_from_calendar = self.get_events_from_calendar(calendar["id"],max_events)
      calendar_data = self.extract_calendar(calendar, include_id = calendars_with_id)
      if calendar_info is True:
        self.add_calendar_info_to_events(events_from_calendar, calendar_data)
      events.extend(events_from_calendar)
    events.sort(key=lambda e: dateutil.parser.parse(e["start"]).replace(tzinfo=timezone.utc) if dateutil.parser.parse(e["start"]).tzinfo is None else dateutil.parser.parse(e["start"]))
    events = events[:max_events]
    return events

  def get_calendars(self, include_id = True):
    calendars = []
    pagetoken = None
    while True:
      result = None
      result = self.service.calendarList().list(pageToken = pagetoken).execute()
      for calendar in result.get("items",[]):
        calendars.append(self.extract_calendar(calendar, include_id))
      pagetoken = result.get("nextPageToken",None)
      if pagetoken is None:
        break
    return calendars

  def extract_calendar(self, calendar, include_id = True):
    new_calendar = {}
    if include_id is True:
      new_calendar["id"] = calendar["id"]
    if "title" in calendar:
      new_calendar["title"] = calendar["title"]
    elif "summary" in calendar:
      new_calendar["title"] = calendar["summary"]
    return new_calendar

  def get_events_from_calendar(self, calendar_id, max_events = None):
    current_events = 0
    pagetoken = None
    events = []
    time = datetime.now(timezone.utc).astimezone().isoformat()
    while max_events is None or current_events<max_events:
      result = None
      result = self.service.events().list(maxResults = max_events, singleEvents = True, orderBy = "startTime",
                                          timeMin = time, maxAttendees = 1, calendarId = calendar_id,
                                          pageToken = pagetoken).execute()
      for event in result.get("items",[]):
        events.append(self.extract_event(event))
        current_events += 1
        if max_events is not None and current_events >= max_events:
          break
      pagetoken = result.get("nextPageToken",None)
      if pagetoken is None:
        break
    return events

  def extract_event(self, event):
    new_event = {}
    new_event["title"] = event["summary"]
    if "date" in event["start"]:
      new_event["start"] = event["start"]["date"]
    elif "dateTime" in event["start"]:
      new_event["start"] = event["start"]["dateTime"]
    if "date" in event["end"]:
      new_event["end"] = event["end"]["date"]
    elif "dateTime" in event["end"]:
      new_event["end"] = event["end"]["dateTime"]
    if "location" in event:
      new_event["location"] = event["location"]
    if "displayName" in event["creator"]:
      new_event["creator"] = event["creator"]["displayName"]
    elif "email" in event["creator"]:
      new_event["creator"] = event["creator"]["email"]
    if "displayName" in event["organizer"]:
      new_event["organizer"] = event["organizer"]["displayName"]
    elif "email" in event["organizer"]:
      new_event["organizer"] = event["organizer"]["email"]
    return new_event

  def add_calendar_info_to_events(self, events, calendar):
    for event in events:
      self.add_calendar_info_to_event(event, calendar)

  def add_calendar_info_to_event(self, event, calendar):
    event["calendar_info"] = calendar
