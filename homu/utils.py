import json
import github3
import logging
import subprocess
import sys
import traceback
import requests
import time


def github_set_ref(repo, ref, sha, *, force=False, auto_create=True):
    url = repo._build_url('git', 'refs', ref, base_url=repo._api)
    data = {'sha': sha, 'force': force}

    try:
        js = repo._json(repo._patch(url, data=json.dumps(data)), 200)
    except github3.models.GitHubError as e:
        if e.code == 422 and auto_create:
            try:
                return repo.create_ref('refs/' + ref, sha)
            except github3.models.GitHubError:
                raise e
        else:
            raise

    return github3.git.Reference(js, repo) if js else None


class Status(github3.repos.status.Status):
    def __init__(self, info):
        super(Status, self).__init__(info)

        self.context = info.get('context')


def github_iter_statuses(repo, sha):
    url = repo._build_url('statuses', sha, base_url=repo._api)
    return repo._iter(-1, url, Status)


def github_create_status(repo, sha, state, target_url='', description='', *,
                         context=''):
    data = {'state': state, 'target_url': target_url,
            'description': description, 'context': context}
    url = repo._build_url('statuses', sha, base_url=repo._api)
    js = repo._json(repo._post(url, data=data), 201)
    return Status(js) if js else None


def remove_url_keys_from_json(json):
    if isinstance(json, dict):
        return {key: remove_url_keys_from_json(value)
                for key, value in json.items()
                if not key.endswith('url')}
    elif isinstance(json, list):
        return [remove_url_keys_from_json(value) for value in json]
    else:
        return json


def lazy_debug(logger, f):
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f())


def logged_call(args, env=None):
    print('* Running command: {}'.format(args))
    try:
        popen = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, env=env)
        for stdout_line in iter(popen.stdout.readline, ""):
          print(stdout_line.strip())
        popen.stdout.close()
        return_code = popen.wait()
        if return_code:
          raise subprocess.CalledProcessError(return_code, args)
    except subprocess.CalledProcessError:
        print('* Failed to execute command: {}'.format(args))
        raise


def silent_call(args):
    return subprocess.call(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def retry_until(inner, fail, state):
    err = None
    exc_info = None

    for i in range(3, 0, -1):
        try:
            inner()
        except (github3.models.GitHubError, requests.exceptions.RequestException) as e:
            print('* Intermittent GitHub error: {}'.format(e), file=sys.stderr)

            err = e
            exc_info = sys.exc_info()

            if i != 1:
                time.sleep(1)
        else:
            err = None
            break

    if err:
        print('* GitHub failure in {}'.format(state), file=sys.stderr)
        traceback.print_exception(*exc_info)

        fail(err)
