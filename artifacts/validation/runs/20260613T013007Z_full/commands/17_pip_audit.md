# pip_audit

- status: failed
- command: `/usr/bin/python3 -m pip_audit`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-13T01:33:59.989129+00:00
- end_time: 2026-06-13T01:34:00.825005+00:00
- duration_seconds: 0.84
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text

```

## stderr

```text
Traceback (most recent call last):
  File "/usr/lib/python3/dist-packages/urllib3/connection.py", line 203, in _new_conn
    sock = connection.create_connection(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3/dist-packages/urllib3/util/connection.py", line 85, in create_connection
    raise err
  File "/usr/lib/python3/dist-packages/urllib3/util/connection.py", line 73, in create_connection
    sock.connect(sa)
ConnectionRefusedError: [Errno 111] Connection refused

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/usr/lib/python3/dist-packages/urllib3/connectionpool.py", line 777, in urlopen
    self._prepare_proxy(conn)
  File "/usr/lib/python3/dist-packages/urllib3/connectionpool.py", line 1058, in _prepare_proxy
    conn.connect()
  File "/usr/lib/python3/dist-packages/urllib3/connection.py", line 611, in connect
    self.sock = sock = self._new_conn()
                       ^^^^^^^^^^^^^^^^
  File "/usr/lib/python3/dist-packages/urllib3/connection.py", line 218, in _new_conn
    raise NewConnectionError(
urllib3.exceptions.NewConnectionError: <urllib3.connection.HTTPSConnection object at 0x7e89c2397c50>: Failed to establish a new connection: [Errno 111] Connection refused

The above exception was the direct cause of the following exception:

urllib3.exceptions.ProxyError: ('Unable to connect to proxy', NewConnectionError('<urllib3.connection.HTTPSConnection object at 0x7e89c2397c50>: Failed to establish a new connection: [Errno 111] Connection refused'))

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/usr/lib/python3/dist-packages/requests/adapters.py", line 486, in send
    resp = conn.urlopen(
           ^^^^^^^^^^^^^
  File "/usr/lib/python3/dist-packages/urllib3/connectionpool.py", line 845, in urlopen
    retries = retries.increment(
              ^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3/dist-packages/urllib3/util/retry.py", line 517, in increment
    raise MaxRetryError(_pool, url, reason) from reason  # type: ignore[arg-type]
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
urllib3.exceptions.MaxRetryError: HTTPSConnectionPool(host='pypi.org', port=443): Max retries exceeded with url: /pypi/aiodns/3.1.1/json (Caused by ProxyError('Unable to connect to proxy', NewConnectionError('<urllib3.connection.HTTPSConnection object at 0x7e89c2397c50>: Failed to establish a new connection: [Errno 111] Connection refused')))

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/home/harshit/.local/lib/python3.12/site-packages/pip_audit/__main__.py", line 8, in <module>
    audit()
  File "/home/harshit/.local/lib/python3.12/site-packages/pip_audit/_cli.py", line 554, in audit
    for spec, vulns in auditor.audit(source):
  File "/home/harshit/.local/lib/python3.12/site-packages/pip_audit/_audit.py", line 68, in audit
    for dep, vulns in self._service.query_all(specs):
  File "/home/harshit/.local/lib/python3.12/site-packages/pip_audit/_service/interface.py", line 180, in query_all
    yield self.query(spec)
          ^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/pip_audit/_service/pypi.py", line 64, in query
    response: requests.Response = self.session.get(url=url, timeout=self.timeout)
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3/dist-packages/requests/sessions.py", line 602, in get
    return self.request("GET", url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3/dist-packages/requests/sessions.py", line 589, in request
    resp = self.send(prep, **send_kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3/dist-packages/requests/sessions.py", line 703, in send
    r = adapter.send(request, **kwargs)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/cachecontrol/adapter.py", line 76, in send
    resp = super().send(request, stream, timeout, verify, cert, proxies)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3/dist-packages/requests/adapters.py", line 513, in send
    raise ProxyError(e, request=request)
requests.exceptions.ProxyError: HTTPSConnectionPool(host='pypi.org', port=443): Max retries exceeded with url: /pypi/aiodns/3.1.1/json (Caused by ProxyError('Unable to connect to proxy', NewConnectionError('<urllib3.connection.HTTPSConnection object at 0x7e89c2397c50>: Failed to establish a new connection: [Errno 111] Connection refused')))

```
