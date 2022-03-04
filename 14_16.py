import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
import logging

EMPTY_TREE_SHA = u"4b825dc642cb6eb9a060e54bf8d69288fbee4904"

class CommitHistory(object):

    def __init__(self, location):
        self.cache = dict()
        self.location = os.path.expanduser(location)
        self.load(self.location)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()

    def load(self, location):
        if os.path.exists(location):
            self._load()
        else:
            logging.debug("Cache file \'{location}\' does not exists".format(location=location))
        return True

    def _load(self):
        # self.cache = set(open(self.location, "r").read().splitlines())
        self.cache = json.loads(open(self.location, "r").read())
        for ref, elems in self.cache.items():
            self.cache[ref] = set(elems)

    def dump(self):
        try:
            # open(self.location, "w+").write('\n'.join(self.cache.__iter__()))
            open(self.location, "w+").write(json.dumps(self.cache, cls=SetEncoder))
            return True
        except Exception as e:
            logging.error(e, exc_info=DEBUG)
            return False

    def for_ref(self, ref):
        if ref in self.cache:
            return self.cache[ref]
        else:
            self.cache[ref] = set()
            return self.cache[ref]

    def add(self, ref, element):
        if ref in self.cache:
            self.cache[ref].add(element)
        else:
            self.cache[ref] = set()
            self.cache[ref].add(element)
        self.dump()
        return True

    def update(self, ref, elements):
        if ref in self.cache:
            self.cache[ref].update(elements)
        else:
            self.cache[ref] = set()
            self.cache[ref].update(elements)
        self.dump()
        return True

    def find(self, ref, element):
        if ref in self.cache:
            return element in self.cache[ref]
        else:
            return False

    def delete(self, ref, element):
        if ref in self.cache:
            self.cache[ref].discard(element)
        return True

    def reset(self):
        self.cache = {}
        self.dump()
        return True

cache = CommitHistory(location=CACHE_FILE)


def get_branch_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "heads" not in line:
            continue

        line = line.replace("refs/heads/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def get_remotes_list():
    branches = list()
    output = execute(COMMAND_REF_LIST)

    for line in output.splitlines():
        if "HEAD" in line:
            continue
        if "remotes" not in line:
            continue

        line = line.replace("refs/remotes/origin/", "")
        line = (line.split()[0], line.split()[2])

        branches.append(line)
    return branches


def _get_last_commit_sha(key):
    sha = database.get(key)
    if sha is False:
        sha = EMPTY_TREE_SHA
    return sha


def get_sha_list(start, end):
    sha_list = list()
    output = execute(COMMAND_COMMIT_SHA_LIST.format(start, end))
    for line in output.splitlines():
        line = line.rstrip().lstrip()
        sha_list.append(line)
    return sha_list


def performSync(remotes=False, force=False, blame=False):
    import time
    start_time = time.time()

    if remotes:
        branches = get_remotes_list()
    else:
        branches = get_branch_list()

    for (end_sha, branch) in branches:
        start_sha = EMPTY_TREE_SHA
        try:
            last_sha = _get_last_commit_sha(branch)

            if last_sha == end_sha and force is False:
                continue

            if last_sha != start_sha and force is False:
                start_sha = last_sha

            sha_list = get_sha_list(start_sha, end_sha)
            logging.debug("{} {}".format(branch, len(sha_list)))

            sha_list = list(set(sha_list) - set(cache.for_ref(branch)))

            logging.debug("{} {} new".format(branch, len(sha_list)))
            for chunk in _chunked_list(sha_list, COMMIT_COUNT):

                commit_chunk = get_commit_list(chunk, remotes=remotes, blame=blame)
                data = wrap_push_event(branch, commit_chunk)
                status_code, content = request(EVENT_PUSH, data)
                logging.debug(
                    "Branch '{}' commit '{}' status '{}' response '{}'".format(branch, chunk[-1], status_code, content))
                if status_code in [200, 201]:
                    _set_last_commit_sha(branch, chunk[-1])
                    cache.update(branch, chunk)
                    time.sleep(5)
                else:
                    logging.error(
                        "Error send chunk to server. Branch '{}' commit '{}' status '{}' response '{}'".format(
                            branch, chunk[-1], status_code, content))
                    time.sleep(15)
                    break

        except Exception as e:
            logging.error("Error some operation with branch. Branch '{}' commit '{}' msg '{}'".format(
                branch, end_sha, e.message), exc_info=DEBUG)
            time.sleep(15)

    time.sleep(15)
    tags = get_tag_list()

    for (tag_sha, tag) in tags:
        end_sha = tag_sha

        commit_list = get_tag_sha_list('tags/' + tag)

        if len(commit_list) > 0:
            end_sha = commit_list[-1]

        last_sha = _get_last_commit_sha(tag)

        if last_sha == end_sha and force is False:
            continue

        data = wrap_tag_event(tag, end_sha)
        logging.debug("Tag '{}' send wrapped data '{}'".format(tag, data))

        status_code, content = request(EVENT_CREATE, data)
        logging.debug(
            "Tag '{}' commit '{}' status '{}' response '{}'".format(tag, end_sha, status_code, content))
        if status_code in [200, 201]:
            _set_last_commit_sha(tag, end_sha)

        time.sleep(10)

    end_time = time.time()
    logging.debug("Total {} seconds".format(end_time - start_time))
    return None


if __name__ == "__main__":

    current_script_name = os.path.basename(__file__)

    if "sync" in sys.argv:
        remotes = force = False
        blame = False

        if '-r' in sys.argv:
            remotes = True
        if '-f' in sys.argv:
            force = True
        if '--no-blame' in sys.argv:
            blame = False
        if '--blame' in sys.argv:
            blame = True
        lock = FileLock(DB_FILE)
        try:
            lock.acquire()
            result = performSync(remotes=remotes, force=force, blame=blame)
            if result:
                sys.exit(0)
            sys.exit(1)
        except MemoryError:
            lock.release()
        except Exception as e:
            traceback.print_exc()
        finally:
            lock.release()
