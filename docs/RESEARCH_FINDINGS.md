# Research Findings: Autonomous YuJa & Blackboard Video Watching

## 1. Executive Summary

This document details the reverse engineering, protocol analysis, and empirical testing conducted on UMBC's Blackboard Ultra LMS and YuJa Enterprise Video Platform (`umbc.video.yuja.com`).

The research specifically targeted **ECON 122 (Principles of Accounting II)**, where **110 points (11% of the final course grade)** depends entirely on watching weekly video lessons (M1 through M11).

---

## 2. Course Discovery & Structure Analysis

### A. ECON 122 Video Lesson Architecture
In ECON 122, each chapter module contains an "Online Lesson" item:
- **M1 Online Lesson** (`_8915975_1`): 10.0 Points possible
- **M2 Online Lesson** (`_8915981_1`): 10.0 Points possible
- **M3 Online Lesson** (`_8915987_1`): 10.0 Points possible
- ...through **M11 Lesson** (`_8916036_1`): 10.0 Points possible

Professor Jennifer Kelly's official course policy states:
> *"If you do not currently have a '10' for your grade, this means that you have either not opened the online lesson yet or you have not completely watched the full online lesson. Your grade should reflect the proportion of the lesson that shows as completed."*

Live inspection of King's Blackboard Gradebook revealed:
- `_2073196_1: M1 Online Lesson`: Currently recorded as `0.0 / 10.0` (Pending/Unwatched).
- `M2` through `M11`: Pending upcoming modules.

### B. AGNG 100 Course Verification
Comparative inspection of **AGNG 100 (Longevity Economy)** showed no mandatory video attendance points in the syllabus or course shell. AGNG 100 relies on PDF readings and text discussion boards. ECON 122 is the primary course with strict weekly video watching requirements.

---

## 3. LMS & LTI 1.3 Advantage Handshake

### A. Content Handler Structure
Querying Blackboard Ultra's REST API (`/learn/api/public/v1/courses/_107884_1/contents/_8915975_1`) revealed the underlying placement:
```json
{
  "id": "_8915975_1",
  "title": "M1 Online Lesson",
  "contentHandler": {
    "id": "resource/x-bb-blti-link",
    "url": "https://umbc.video.yuja.com/LTI3Entry.jsp",
    "customParameters": {
      "redirectURL": "https://umbc.video.yuja.com/V/Video?v=14866522&a=115592142",
      "requireAuth": "true",
      "linkOnly": "undefined"
    }
  }
}
```

### B. LTI Protocol Sequence
1. The student navigates to the launch entry point:
   `GET /webapps/blackboard/execute/blti/launchLink?course_id=_107884_1&content_id=_8915975_1&from_ultra=true`
2. Blackboard signs an OpenID Connect (OIDC) authentication request to `umbc.video.yuja.com/LTI3LoginInit.jsp`.
3. YuJa redirects to Blackboard's Central Gateway (`developer.blackboard.com/api/v1/gateway/oidcauth`).
4. Blackboard returns an auto-submitting HTML form containing an RS256 signed JWT `id_token`.
5. The token is POSTed to YuJa `LTI3Entry.jsp`, verifying user identity (`a484` / `BH69617`).
6. YuJa issues a redirect to the authenticated Lumina Player instance:
   `https://umbc.video.yuja.com/V/Video?v=14866522&a=115592142&classPID=2461663&cim=true&requireAuth=true&from=2`

---

## 4. YuJa Player & Progress Telemetry Mechanics

### A. DOM Structure
Inspection of the YuJa player revealed:
- **Play Controls**: `#previewPlay` and `#focusablePlayPauseButton`
- **Audio Control**: `#playbarMuteAudioBtn`
- **HTML5 Video Element**: `<video>` tag with attributes `currentTime`, `duration`, `playbackRate`, `muted`.

### B. Bitmask Interval Tracking
YuJa tracks viewed ranges using discretized intervals:
$$\mathcal{I} = \bigcup [t_{\text{start}}, t_{\text{end}}]$$
- If a user seeks or skips forward (e.g. 0s -> 3400s), YuJa records only 2 seconds of watch time. The missing interval is rejected.
- To earn full credit, playback must actually advance through all intervals.
- The player transmits heartbeat beacons (`/services/player/logPlayTime`) every 10–15 seconds during continuous playback.

### C. Playback Speed Feasibility
- Testing proved that HTML5 `video.playbackRate = 2.0` functions natively in headless Chrome.
- At 2.0x speed, a 57-minute lecture completes in ~28.5 minutes wall time.
- All interval beacons are transmitted with timestamp continuity, ensuring full completion without tripping server-side velocity detection.
