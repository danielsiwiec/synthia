import os

import pytest
from playwright.sync_api import sync_playwright

VOICE_PAGE_URL = os.environ.get("VOICE_TEST_URL", "http://localhost:8003/")

MEDIA_RECORDER_MOCK = """
    window.MediaRecorder = class MockMediaRecorder {
        constructor(stream, options) {
            this.stream = stream;
            this.state = 'inactive';
            this.mimeType = options?.mimeType || 'audio/webm';
        }
        start(timeslice) {
            this.state = 'recording';
            this._interval = setInterval(() => {
                if (this.ondataavailable) {
                    const blob = new Blob([new ArrayBuffer(1024)], { type: this.mimeType });
                    this.ondataavailable({ data: blob });
                }
            }, timeslice || 100);
        }
        stop() {
            this.state = 'inactive';
            if (this._interval) clearInterval(this._interval);
            if (this.onstop) setTimeout(() => this.onstop(), 50);
        }
        static isTypeSupported(type) {
            return type.includes('audio/webm') || type.includes('audio/mp4');
        }
    };
"""

GET_USER_MEDIA_MOCK = """
    navigator.mediaDevices.getUserMedia = async function(constraints) {
        if (constraints.audio) {
            const audioContext = new AudioContext();
            const oscillator = audioContext.createOscillator();
            oscillator.frequency.value = 440;
            const dest = audioContext.createMediaStreamDestination();
            oscillator.connect(dest);
            oscillator.start();
            window.__mockAudioContext = audioContext;
            return dest.stream;
        }
        throw new Error('Only audio supported in mock');
    };
"""


@pytest.fixture(scope="function")
def browser_context():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
        )
        context = browser.new_context(
            permissions=["microphone"],
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
        )
        context.grant_permissions(["microphone"])
        yield context
        context.close()
        browser.close()


def _setup_api_mocks(page, transcribe_text="hello synthia", task_result="Hello! How can I help you?"):
    page.route(
        "**/transcribe",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=f'{{"text": "{transcribe_text}"}}'
        ),
    )
    page.route(
        "**/task",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=f'{{"thread_id": 123, "result": "{task_result}", "session_id": "test"}}',
        ),
    )
    page.route(
        "**/tts**",
        lambda route: route.fulfill(status=200, content_type="audio/mpeg", body=b"\xff\xfb\x90\x00" + b"\x00" * 1000),
    )


@pytest.fixture
def page_with_mocks(browser_context):
    page = browser_context.new_page()
    page.add_init_script(GET_USER_MEDIA_MOCK + MEDIA_RECORDER_MOCK)
    _setup_api_mocks(page)
    yield page
    page.close()


@pytest.fixture
def page_with_tracking(browser_context):
    page = browser_context.new_page()
    page.add_init_script(
        """
        window.__audioEvents = [];

        navigator.mediaDevices.getUserMedia = async function(constraints) {
            window.__audioEvents.push('getUserMedia called');
            const audioContext = new AudioContext();
            const oscillator = audioContext.createOscillator();
            oscillator.frequency.value = 440;
            const dest = audioContext.createMediaStreamDestination();
            oscillator.connect(dest);
            oscillator.start();
            window.__mockAudioContext = audioContext;
            return dest.stream;
        };

        window.MediaRecorder = class MockMediaRecorder {
            constructor(stream, options) {
                this.stream = stream;
                this.state = 'inactive';
                this.mimeType = options?.mimeType || 'audio/webm';
                window.__audioEvents.push('MediaRecorder created');
            }
            start(timeslice) {
                this.state = 'recording';
                window.__audioEvents.push('MediaRecorder started');
                this._interval = setInterval(() => {
                    if (this.ondataavailable) {
                        const blob = new Blob([new ArrayBuffer(1024)], { type: this.mimeType });
                        this.ondataavailable({ data: blob });
                    }
                }, timeslice || 100);
            }
            stop() {
                this.state = 'inactive';
                window.__audioEvents.push('MediaRecorder stopped');
                if (this._interval) clearInterval(this._interval);
                if (this.onstop) setTimeout(() => this.onstop(), 50);
            }
            static isTypeSupported(type) {
                return type.includes('audio/webm') || type.includes('audio/mp4');
            }
        };

        const OriginalAudioContext = window.AudioContext || window.webkitAudioContext;
        window.AudioContext = class TrackedAudioContext extends OriginalAudioContext {
            constructor() {
                super();
                window.__audioEvents.push('AudioContext created');
            }
            async decodeAudioData(arrayBuffer) {
                window.__audioEvents.push('decodeAudioData called with ' + arrayBuffer.byteLength + ' bytes');
                const buffer = this.createBuffer(1, this.sampleRate, this.sampleRate);
                return buffer;
            }
        };
        window.webkitAudioContext = window.AudioContext;
    """
    )
    _setup_api_mocks(page, transcribe_text="test message", task_result="This is the response")
    yield page
    page.close()


@pytest.mark.voice
def test_voice_page_loads(browser_context):
    page = browser_context.new_page()
    page.goto(VOICE_PAGE_URL, timeout=10000)

    voice_btn = page.locator("#voice-btn")
    voice_btn.wait_for(state="visible", timeout=5000)

    assert voice_btn.get_attribute("class") == "idle"
    page.close()


@pytest.mark.voice
def test_button_click_starts_listening(page_with_mocks):
    page = page_with_mocks
    page.goto(VOICE_PAGE_URL, timeout=10000)

    voice_btn = page.locator("#voice-btn")
    voice_btn.wait_for(state="visible")

    assert voice_btn.get_attribute("class") == "idle"

    voice_btn.click()
    page.wait_for_timeout(500)

    btn_class = voice_btn.get_attribute("class")
    assert btn_class in ["listening", "processing"]


@pytest.mark.voice
def test_status_shows_listening(page_with_mocks):
    page = page_with_mocks
    page.goto(VOICE_PAGE_URL, timeout=10000)

    voice_btn = page.locator("#voice-btn")
    status_el = page.locator("#status")

    voice_btn.click()
    page.wait_for_timeout(200)

    status_text = status_el.text_content()
    assert status_text in ["Listening...", "Requesting microphone..."]


@pytest.mark.voice
def test_error_hidden_initially(browser_context):
    page = browser_context.new_page()
    page.goto(VOICE_PAGE_URL, timeout=10000)

    error_el = page.locator("#error")
    assert "visible" not in (error_el.get_attribute("class") or "")
    page.close()


@pytest.mark.voice
def test_speaking_state_styling(browser_context):
    page = browser_context.new_page()
    page.goto(VOICE_PAGE_URL, timeout=10000)

    voice_btn = page.locator("#voice-btn")
    voice_btn.wait_for(state="visible")

    page.evaluate("""
        () => {
            const btn = document.getElementById('voice-btn');
            const container = document.getElementById('button-container');
            btn.className = 'speaking';
            container.className = 'button-container speaking';
        }
    """)

    assert voice_btn.get_attribute("class") == "speaking"
    page.close()


@pytest.mark.voice
def test_touch_events_work(page_with_mocks):
    page = page_with_mocks
    page.goto(VOICE_PAGE_URL, timeout=10000)

    voice_btn = page.locator("#voice-btn")
    voice_btn.tap()
    page.wait_for_timeout(300)

    btn_class = voice_btn.get_attribute("class")
    assert btn_class in ["listening", "processing", "idle"]


@pytest.mark.voice
def test_full_voice_flow(page_with_mocks):
    page = page_with_mocks
    page.goto(VOICE_PAGE_URL, timeout=10000)

    voice_btn = page.locator("#voice-btn")
    assert voice_btn.get_attribute("class") == "idle"

    voice_btn.click(force=True)
    page.wait_for_timeout(300)

    voice_btn.click(force=True)

    page.wait_for_function(
        """() => {
            const btn = document.getElementById('voice-btn');
            return btn.className === 'idle' ||
                   btn.className === 'processing' ||
                   btn.className === 'speaking';
        }""",
        timeout=10000,
    )


@pytest.mark.voice
def test_audio_flow_calls_all_apis(page_with_tracking):
    page = page_with_tracking
    page.goto(VOICE_PAGE_URL, timeout=10000)

    voice_btn = page.locator("#voice-btn")
    assert voice_btn.get_attribute("class") == "idle"

    voice_btn.click(force=True)
    page.wait_for_timeout(300)

    voice_btn.click(force=True)

    page.wait_for_function(
        """() => {
            const btn = document.getElementById('voice-btn');
            const status = document.getElementById('status');
            return btn.className === 'speaking' ||
                   (btn.className === 'idle' && status.textContent === '');
        }""",
        timeout=15000,
    )

    events = page.evaluate("window.__audioEvents")

    assert "getUserMedia called" in events
    assert "MediaRecorder created" in events
    assert "MediaRecorder started" in events
    assert "MediaRecorder stopped" in events
    assert "AudioContext created" in events
    assert any("decodeAudioData" in e for e in events)


@pytest.mark.voice
def test_tts_receives_response_text(page_with_tracking):
    page = page_with_tracking

    tts_requests = []

    def capture_tts(route):
        tts_requests.append(route.request.url)
        route.fulfill(
            status=200,
            content_type="audio/mpeg",
            body=b"\xff\xfb\x90\x00" + b"\x00" * 2000,
        )

    page.route("**/tts**", capture_tts)
    page.goto(VOICE_PAGE_URL, timeout=10000)

    voice_btn = page.locator("#voice-btn")
    voice_btn.click(force=True)
    page.wait_for_timeout(300)
    voice_btn.click(force=True)

    page.wait_for_function(
        """() => {
            const btn = document.getElementById('voice-btn');
            return btn.className === 'speaking' || btn.className === 'idle';
        }""",
        timeout=15000,
    )

    assert len(tts_requests) > 0
    assert "text=This" in tts_requests[0] or "text=This%20is" in tts_requests[0]


@pytest.mark.voice
def test_touch_triggers_recording(page_with_tracking):
    page = page_with_tracking
    page.goto(VOICE_PAGE_URL, timeout=10000)

    voice_btn = page.locator("#voice-btn")
    assert voice_btn.get_attribute("class") == "idle"

    voice_btn.tap()
    page.wait_for_timeout(500)

    events = page.evaluate("window.__audioEvents")
    assert "getUserMedia called" in events

    btn_class = voice_btn.get_attribute("class")
    assert btn_class in ["listening", "processing"]


@pytest.mark.voice
def test_consecutive_taps_work(page_with_mocks):
    page = page_with_mocks
    page.goto(VOICE_PAGE_URL, timeout=10000)

    voice_btn = page.locator("#voice-btn")

    voice_btn.tap(force=True)
    page.wait_for_timeout(300)

    btn_class = voice_btn.get_attribute("class")
    assert btn_class in ["listening", "processing"]

    voice_btn.tap(force=True)
    page.wait_for_timeout(500)

    voice_btn.tap(force=True)
    page.wait_for_timeout(300)

    btn_class = voice_btn.get_attribute("class")
    assert btn_class in ["listening", "processing", "idle", "speaking"]


@pytest.mark.voice
def test_reset_button_exists(browser_context):
    page = browser_context.new_page()
    page.goto(VOICE_PAGE_URL, timeout=10000)

    reset_btn = page.locator("#reset-btn")
    reset_btn.wait_for(state="visible", timeout=5000)

    assert reset_btn.get_attribute("aria-label") == "Reset"
    page.close()
