# Choice on Windows (background service)

Run Choice on the machine that holds your photos or config. Bind to loopback only unless you intend LAN use.

## Install

1. Install [Python 3.11+](https://www.python.org/downloads/windows/) and tick **Add python.exe to PATH**.
2. Unzip `choice-0.2.1.zip` to a folder, e.g. `C:\Apps\choice`.
3. Open **Command Prompt** or PowerShell:

```text
cd C:\Apps\choice
python -m pip install .
```

Copy `choice.example.toml` to `choice.toml`, edit sources and decks, then store secrets outside the config if needed.

## Run in the foreground (smoke test)

```text
python -m choice --host 127.0.0.1 --config C:\Apps\choice\choice.toml
```

Open `http://127.0.0.1:8741/` in a browser. Stop with Ctrl+C.

## Behind a path prefix

If a reverse proxy serves Choice at `https://photos.example.com/choice/`:

```text
python -m choice --host 127.0.0.1 --port 8741 --config C:\Apps\choice\choice.toml --base-path /choice
```

Use the same `/choice` prefix on the proxy. The printed URL includes the base path.

## Background service (NSSM)

[NSSM](https://nssm.cc/) keeps Choice running without a console window.

1. Download NSSM and run `nssm install Choice`.
2. **Path**: `C:\Users\You\AppData\Local\Programs\Python\Python312\python.exe` (your `python.exe`).
3. **Startup directory**: `C:\Apps\choice`.
4. **Arguments**:

```text
-m choice --host 127.0.0.1 --port 8741 --config C:\Apps\choice\choice.toml --base-path /choice
```

5. Install the service, then start it from **Services** (`services.msc`).

Logs and errors appear in the Windows **Application** event log if the process exits; run once in a console first to fix config mistakes.

## Alternative: Task Scheduler

Create a task that runs at log on, action **Start a program**:

- Program: `python.exe`
- Arguments: same as NSSM **Arguments** above
- Start in: `C:\Apps\choice`

Enable **Run whether user is logged on or not** only if you accept storing credentials for that account.

## Security

`127.0.0.1` accepts connections only from this PC. `--lan` listens on the network; anyone who can reach the port can swipe and move files. A person name in the UI is not a password.
