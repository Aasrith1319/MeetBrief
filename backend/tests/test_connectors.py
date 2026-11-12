"""Official transcript connectors with mocked provider APIs (shapes from the public API docs)."""
import httpx
import pytest

from backend.connectors import ConnectorError, google_meet, teams, zoom


def meet_handler(request):
    p = request.url.path
    if p == "/v2/conferenceRecords":
        assert request.url.params["filter"] == 'space.meeting_code="abc-defg-hij"'
        return httpx.Response(200, json={"conferenceRecords": [
            {"name": "conferenceRecords/old", "startTime": "2026-10-01T09:00:00Z"},
            {"name": "conferenceRecords/r1", "startTime": "2026-10-10T10:00:00Z"}]})
    if p == "/v2/conferenceRecords/r1/transcripts":
        return httpx.Response(200, json={"transcripts": [{"name": "conferenceRecords/r1/transcripts/t1", "state": "FILE_GENERATED",
                                                          "startTime": "2026-10-10T10:00:01Z"}]})
    if p == "/v2/conferenceRecords/r1/transcripts/t1/entries":
        if "pageToken" not in request.url.params:
            return httpx.Response(200, json={"transcriptEntries": [
                {"participant": "conferenceRecords/r1/participants/p1", "text": "The database queries are slow.",
                 "startTime": "2026-10-10T10:00:05Z", "endTime": "2026-10-10T10:00:09Z", "languageCode": "en-US"}],
                "nextPageToken": "next"})
        return httpx.Response(200, json={"transcriptEntries": [
            {"participant": "conferenceRecords/r1/participants/p2", "text": "Priya, please finish the indexing by Friday.",
             "startTime": "2026-10-10T10:02:00Z", "endTime": "2026-10-10T10:02:04Z"}]})
    if p == "/v2/conferenceRecords/r1/participants/p1":
        return httpx.Response(200, json={"signedinUser": {"displayName": "Priya Sharma"}})
    if p == "/v2/conferenceRecords/r1/participants/p2":
        return httpx.Response(200, json={"signedinUser": {"displayName": "Rahul Verma"}})
    return httpx.Response(404)


def test_google_meet_connector():
    http = httpx.Client(transport=httpx.MockTransport(meet_handler))
    title, segs = google_meet.fetch("https://meet.google.com/abc-defg-hij?authuser=0", "tok", http)
    assert [s.speaker_name for s in segs] == ["Priya Sharma", "Rahul Verma"]
    assert segs[0].start_time == 5 and segs[1].start_time == 120
    assert segs[0].language == "en"
    with pytest.raises(ConnectorError):
        google_meet.fetch("not a meet link", "tok", http)


def test_google_meet_no_transcript_and_auth_errors():
    def handler(request):
        if request.url.path == "/v2/conferenceRecords":
            return httpx.Response(200, json={"conferenceRecords": [{"name": "conferenceRecords/r1", "startTime": "x"}]})
        if request.url.path.endswith("/transcripts"):
            return httpx.Response(200, json={"transcripts": [{"name": "t", "state": "STARTED"}]})
        return httpx.Response(404)
    with pytest.raises(ConnectorError, match="no transcript"):
        google_meet.fetch("abc-defg-hij", "tok", httpx.Client(transport=httpx.MockTransport(handler)))
    forbidden = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    with pytest.raises(ConnectorError, match="Not authorised"):
        google_meet.fetch("abc-defg-hij", "tok", forbidden)


def test_zoom_connector():
    vtt = "WEBVTT\n\n1\n00:00:05.000 --> 00:00:09.000\nPriya Sharma: The queries are slow.\n\n2\n00:02:00.000 --> 00:02:04.000\nRahul: Let's add indexing first.\n"

    def handler(request):
        if request.url.path == "/v2/meetings/81234567890/recordings":
            assert request.headers["Authorization"] == "Bearer tok"
            return httpx.Response(200, json={"topic": "Weekly sync", "recording_files": [
                {"file_type": "MP4", "download_url": "https://zoom.us/rec/x.mp4"},
                {"file_type": "TRANSCRIPT", "status": "completed", "download_url": "https://zoom.us/rec/download/t.vtt"}]})
        if request.url.path == "/rec/download/t.vtt":
            return httpx.Response(200, text=vtt)
        return httpx.Response(404)
    title, segs = zoom.fetch("https://us02web.zoom.us/j/81234567890?pwd=abc", "tok", httpx.Client(transport=httpx.MockTransport(handler)))
    assert title == "Weekly sync" and [s.speaker_name for s in segs] == ["Priya Sharma", "Rahul"]
    assert zoom.meeting_id("812 3456 7890") == "81234567890"


def test_teams_connector():
    link = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_x%40thread.v2/0?context=%7b%7d"
    vtt = "WEBVTT\n\n00:00:05.000 --> 00:00:09.000\n<v Priya Sharma>The queries are slow.</v>\n\n00:02:00.000 --> 00:02:04.000\n<v Rahul>Let's add indexing first.</v>\n"

    def handler(request):
        p = request.url.path
        if p == "/v1.0/me/onlineMeetings":
            assert request.url.params["$filter"] == f"JoinWebUrl eq '{link}'"
            return httpx.Response(200, json={"value": [{"id": "m1", "subject": "Design review"}]})
        if p == "/v1.0/me/onlineMeetings/m1/transcripts":
            return httpx.Response(200, json={"value": [{"id": "t1", "createdDateTime": "2026-10-10T10:30:00Z"}]})
        if p == "/v1.0/me/onlineMeetings/m1/transcripts/t1/content":
            return httpx.Response(200, text=vtt)
        return httpx.Response(404)
    title, segs = teams.fetch(link, "tok", httpx.Client(transport=httpx.MockTransport(handler)))
    assert title == "Design review" and [s.speaker_name for s in segs] == ["Priya Sharma", "Rahul"]


def test_import_endpoint_replaces_room_transcript(client, monkeypatch):
    from backend.config import settings
    from backend.connectors import google_meet as gm

    monkeypatch.setattr(settings, "rooms_dev_auth", True)
    real = gm.fetch
    monkeypatch.setattr(gm, "fetch", lambda ref, tok, client=None: real(ref, tok, httpx.Client(transport=httpx.MockTransport(meet_handler))))
    h = {"X-MeetBrief-Dev-User": "Priya <priya@college.edu>", "X-MeetBrief-Token": ""}
    room = client.post("/api/rooms/share", headers=h, json={"meeting_key": "google_meet:abc-defg-hij", "in_call": True}).json()
    client.post(f"/api/rooms/{room['id']}/segments", headers=h, json={"segments": [{"text": "partial live line", "speaker_name": "Priya"}]})
    r = client.post("/api/import/google_meet", headers=h, json={"meeting_ref": "abc-defg-hij", "access_token": "x" * 20,
                                                                "meeting_id": room["meeting_id"]})
    assert r.status_code == 200 and r.json()["added"] == 2
    segs = client.get(f"/api/meetings/{room['meeting_id']}/segments", headers=h).json()["segments"]
    assert [s["speaker_name"] for s in segs] == ["Priya Sharma", "Rahul Verma"]  # official transcript replaced the live one
    # a member cannot import into someone else's meeting, nor create meetings
    eve = {"X-MeetBrief-Dev-User": "Eve <eve@evil.com>", "X-MeetBrief-Token": ""}
    assert client.post("/api/import/google_meet", headers=eve, json={"meeting_ref": "abc-defg-hij", "access_token": "x" * 20,
                                                                     "meeting_id": room["meeting_id"]}).status_code == 404
    assert client.post("/api/import/google_meet", headers=eve, json={"meeting_ref": "abc-defg-hij", "access_token": "x" * 20}).status_code == 400
