# Session context: FlightFactor A320 Ultimate XP12 activation failure

Date: 2026-06-17 -> 2026-06-18 MSK

Status: local main-PC issue is now unlikely. The same silent activation failure was reproduced on a second PC with a clean X-Plane 12 installation and no third-party add-ons.

## Problem

FlightFactor A320 Ultimate XP12 Extended does not complete in-sim activation in X-Plane 12.

Observed behavior:

- X-Updater accepts the license key and reports the product as up to date.
- The aircraft loads in X-Plane.
- The in-sim activation dialog accepts the serial/license text.
- After pressing `Activate`, no visible error appears and activation does not complete.
- There is no explicit `invalid key`, `banned key`, `activation limit`, `network`, `SSL/TLS`, `certificate`, `timeout`, or `firewall` error.

Do not store or publish the actual serial/license key in this repository.

## Main PC baseline

Main X-Plane installation:

```text
D:\XP12
X-Plane 12.4.3-r1
Aircraft path:
D:\XP12\Aircraft\FlightFactor\Airbus-A320-Ultimate-12-extended
```

Relevant `Log.txt` lines from the main PC:

```text
[A320U API INFO]: Activation required...
[FF Plugin Manager] SASL not activated, aborting...
FF: Activation required - requesting activation data
```

Main PC `SASLLog.txt`:

```text
[A320U API INFO]: Initializing...
[A320U API INFO]: Activation required...
[A320U API INFO]: Enabling...
[A320U API INFO]: Disabling...
[A320U API INFO]: SASL plugin stopped...
```

## Main PC checks

A manual write test in the A320 aircraft folder succeeded:

```powershell
$aircraft = "D:\XP12\Aircraft\FlightFactor\Airbus-A320-Ultimate-12-extended"
$testFile = Join-Path $aircraft "__write_test.txt"
"test" | Set-Content $testFile -Encoding ASCII
Get-Item $testFile | Select-Object FullName,Length,CreationTime
Remove-Item $testFile
```

Result: file was created and removed successfully. This rules out a simple aircraft-folder write-permission problem.

Search for activation/license/SASL/log files on the main PC showed:

```text
plugins\sasl\data\output\SASLLog.txt    Length 182
modules\serial.key                      Length 32
modules\main.key                        Length 0
modules\data.key                        Length 66
```

Key symptom:

```text
serial.key is created/updated,
main.key is created but remains 0 bytes.
```

Interpretation: the plugin accepts/saves the serial, but the main activation token/license payload is not written.

## Why this does not look like a generic PC/network issue

Already verified:

- X-Updater accepts the A320 key and updates the product.
- Other FlightFactor products, including 757 and 767, install/activate/update successfully in the user's environment.
- X-Plane has working HTTPS connectivity; weather service fetches are visible in `Log.txt`.
- Another plugin, XPRealistic, activated online in the same X-Plane session.
- The A320 aircraft folder is writable.
- No explicit firewall/SSL/TLS/certificate/timeout error is shown in the logs.

## Second-PC clean test

The user installed a clean X-Plane 12 on a different PC with no third-party add-ons or old settings.

Second PC environment:

```text
C:\XPLANE12
X-Plane 12.4.0-b1
CPU: Intel Core i5-12450H
GPU: NVIDIA GeForce RTX 4060 Laptop GPU
RAM: 16 GB
Aircraft path:
C:\XPLANE12\Aircraft\FlightFactor\Airbus-A320-Ultimate-12-extended
```

The same symptom was reproduced on the second PC:

```text
X-Updater accepts the key
A320 loads
SASL starts
in-sim activation accepts the serial
pressing Activate does nothing visible
```

## Key `Log.txt` evidence from the second PC

The clean second-PC log captured the full activation HTTP path:

```text
FF: Activation required - requesting activation data
FF: LWS HTTP client session ..., trying to send 89 bytes...
FF: LWS HTTP client session ..., sent 89 bytes.
FF: LWS HTTP client session ..., sent all data.
FF: LWS HTTP client session ... headers:
  CACHE_CONTROL: no-store, no-cache, must-revalidate, max-age=0;
  PRAGMA: no-cache;
  CONTENT_LENGTH: 0;
  CONTENT_TYPE: text/html; charset=UTF-8;
  DATE: Wed, 17 Jun 2026 21:15:51 GMT;
  SERVER: nginx;
FF: LWS HTTP client session ..., connected.
FF: LWS HTTP client session ... request: [serial masked] :xp12
```

Most important line:

```text
CONTENT_LENGTH: 0
```

Interpretation: the activation request is actually sent, and the FlightFactor/nginx server actually responds, but the response body is empty. For a successful activation, the plugin should receive some activation payload/token that presumably results in a non-empty `modules\main.key`. The empty response explains the silent failure and `main.key = 0 bytes`.

## Current technical conclusion

After reproducing on a second clean PC:

```text
The main PC / Windows installation / hardware / global plugins / old X-Plane environment are unlikely to be the root cause.
```

Most likely causes:

1. FlightFactor server-side activation endpoint returns an empty response for this A320 XP12 serial.
2. The specific license/serial state does not generate an activation payload.
3. A bug in the A320 Ultimate XP12 activation flow / SASL / Plugin Manager.
4. Possible compatibility issue with X-Plane 12.4.x activation flow, but that would still be a product/activation-flow issue rather than a local PC issue.

## Why the logs differed between machines

The main PC's first log did not show `LWS HTTP client ... headers`, while the second PC log did.

Possible explanations:

- `Log.txt` is rewritten every X-Plane launch; the first main-PC log might not have captured the most informative activation attempt.
- X-Plane may have been closed before the HTTP client wrote the headers lines.
- Different X-Plane/A320 builds may differ in logging detail:

```text
main PC:   X-Plane 12.4.3-r1, simulation build rev 2697
second PC: X-Plane 12.4.0-b1, simulation build rev 2694
```

This difference does not weaken the case because the clean second PC captured the key evidence: the request is sent and the server returns an empty body.

## Optional follow-up checks

On the main PC, repeat the activation attempt, wait at least 60 seconds, close X-Plane, then run:

```powershell
Select-String -Path "D:\XP12\Log.txt" -Pattern "Activation required|LWS HTTP|CONTENT_LENGTH|SERVER: nginx|request:" -Context 2,2
```

If `CONTENT_LENGTH: 0` appears on the main PC too, both installations match line-for-line.

On the second PC, record key-file sizes after the failed activation:

```powershell
Get-Item "C:\XPLANE12\Aircraft\FlightFactor\Airbus-A320-Ultimate-12-extended\modules\*.key" |
    Select-Object Name, Length, CreationTime, LastWriteTime |
    Format-Table -AutoSize
```

Expected confirmation:

```text
data.key      66
serial.key    32
main.key       0
```

Do not publish or paste the contents of `.key` files.

## Suggested message to FlightFactor support

```text
I reproduced the same A320 Ultimate XP12 activation failure on a second PC with a clean X-Plane 12 installation and no third-party add-ons.

The issue is not specific to my main PC, Windows installation, firewall, plugins, or hardware.

On both machines:
- X-Updater accepts the license key and installs/updates the aircraft.
- The aircraft loads.
- SASL starts and reports "Activation required".
- Pressing Activate does not show any error and does not complete activation.
- serial.key is created/updated.
- main.key remains 0 bytes.

The clean second-PC Log.txt shows that the activation request is actually sent and the FlightFactor/nginx server responds, but the response has an empty body:

FF: Activation required - requesting activation data
FF: LWS HTTP client session ..., trying to send 89 bytes...
FF: LWS HTTP client session ..., sent 89 bytes.
FF: LWS HTTP client session ..., sent all data.
FF: LWS HTTP client session ... headers:
CONTENT_LENGTH: 0
CONTENT_TYPE: text/html; charset=UTF-8
SERVER: nginx

This looks like the server-side activation endpoint returns an empty response or fails to issue the activation payload/token for this A320 XP12 serial. Please check the server-side activation logs for my serial and explain why the activation response body is empty and why main.key remains 0 bytes.
```

## Privacy warning

Logs and screenshots may contain:

- license/serial values;
- email addresses;
- plugin request bodies with keys or serials.

Before sending logs publicly or to support, redact:

```text
serial/license values
email addresses
request bodies containing keys
```

Use `[serial masked]` in written summaries.
