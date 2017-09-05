# Dependencies

```
apt --no-install-recommends install novnc tigervnc-standalone-server
```

# Starting manually

X/VNC server (no security):

	Xtigervnc -geometry 1000x750 -desktop prova :100 -SecurityTypes None -localhost

X session/client:

	DISPLAY=:100 xeyes

VNC viewer (default port is 5900 + screen number)

	vncviewer localhost:6000

Export VNC port over websocket, and serve web page:

	websockify --web /usr/share/novnc/ 6080 localhost:6000

Web page for viewer:

	http://localhost:6080/vnc.html?host=localhost&port=6080&autoconnect=true

The source parsing the URL arguments is at `/usr/share/novnc/include/ui.js:36`


# `.service` files

`.service` files implement a subset of systemd's unit files. All sections and
configurations that are not supported are silently ignored.


## `[Unit]` section

Currently ignored


## `[Service]` section

These configurations are supported the same as in systemd:

* `SyslogIdentifier`
* `ExecStartPre`
* `ExecStartPost`

These configurations are partially supported:

* `ExecStart`: prefixes `@`, `-`, `+` are ignored
* `WorkingDirectory`: value `~` is not supported


## `[Webrun]` section

The `Webrun` section contains configuration directives that are specific to
webrun:

* `DisplayGeometry` (default: `800x600`): geometry of the X display where the
  application is run
