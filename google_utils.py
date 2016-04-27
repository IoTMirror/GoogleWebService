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