
import time
import wave
import sys
import threading

# ── audioop compatibility ───────────────────────────
try:
    import audioop
except ImportError:
    try:
        import audioop_lts as audioop
    except ImportError:
        print("ERROR: audioop not available. Run: pip install audioop-lts")
        sys.exit(1)

# ── PyVoIP imports ────────────────────────────────
try:
    from pyVoIP.VoIP import VoIPPhone, CallState
except ImportError:
    from pyVoIP.VoIP.VoIP import VoIPPhone
    from pyVoIP.VoIP.call import CallState

try:
    from pyVoIP.VoIP.error import InvalidStateError
except:
    InvalidStateError = Exception

# ── Audio playback ────────────────────────────────
import pyaudio

print(f"Python: {sys.version}")
import pyVoIP
print(f"PyVoIP: {pyVoIP.__version__}")

# ==== CONFIG ====
SIP_SERVER  = "10.1.0.8"
SIP_PORT    = 5060
USERNAME    = "1007"
PASSWORD    = "10071007"

MY_IP       = "10.1.1.33"
SIP_PORT_MY = 5061

CALL_TO     = "0985"
WAV_FILE    = "/root/vasan/embassy_moi_multi/Auriga/Thank you for contac.wav"

# ==== INIT PHONE ====
print("Starting VoIPPhone...")

phone = VoIPPhone(
    SIP_SERVER,
    SIP_PORT,
    USERNAME,
    PASSWORD,
    myIP=MY_IP,
    sipPort=SIP_PORT_MY,
    callCallback=None,   # 🔥 disable callback
    rtpPortLow=10000,
    rtpPortHigh=10100,
)

phone.start()

# ==== WAIT FOR REGISTRATION ====
print("Waiting for registration...")
time.sleep(2)

# ==== MAKE CALL ====
print(f"Calling {CALL_TO}...")
print("SIP socket:", phone.sip.out)

call = None
try:
    call = phone.call(CALL_TO)
except Exception as e:
    print("Call failed:", e)
    phone.stop()
    sys.exit(1)

if not call:
    print("Call not created.")
    phone.stop()
    sys.exit(1)

# ==== WAIT FOR ANSWER ====
print("Waiting for answer...")
while call.state != CallState.ANSWERED:
    print(f"State: {call.state}", end="\r")
    if str(call.state) in ("CallState.ENDED", "ENDED"):
        print("\nCall ended before answer.")
        phone.stop()
        sys.exit(1)
    time.sleep(0.5)


import threading

def record_audio(call):
    import wave

    wf = wave.open("received_audio.wav", "wb")
    wf.setnchannels(1)
    wf.setsampwidth(2)   # 16-bit
    wf.setframerate(8000)

    print("🎧 Recording incoming audio...")

    while call.state == CallState.ANSWERED:
        try:
            data = call.read_audio()

            if data:
                wf.writeframes(data)

        except Exception as e:
            print("Recording error:", e)
            break

        time.sleep(0.02)

    wf.close()
    print("✅ Saved received_audio.wav")

print("\n✅ Call ANSWERED!")

threading.Thread(target=record_audio, args=(call,), daemon=True).start()

# =========================================================
# 🔊 AUDIO PLAYBACK THREAD (incoming audio)
# =========================================================
def play_audio(call):
    import pyaudio
    import audioop

    p = pyaudio.PyAudio()

    OUTPUT_RATE = 44100  # 🔥 supported by your system
    INPUT_RATE = 8000

    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=OUTPUT_RATE,
        output=True
    )

    print("🔊 Listening (resampled)...")

    state = None

    while call.state == CallState.ANSWERED:
        try:
            data = call.read_audio()

            if data:
                # 🔥 RESAMPLE 8k → 44.1k
                data, state = audioop.ratecv(
                    data,
                    2,        # 16-bit
                    1,        # mono
                    INPUT_RATE,
                    OUTPUT_RATE,
                    state
                )

                stream.write(data)

        except Exception as e:
            print("Playback error:", e)
            break

        time.sleep(0.02)

    stream.stop_stream()
    stream.close()
    p.terminate()
    print("Playback stopped.")

# Start listening thread
threading.Thread(target=play_audio, args=(call,), daemon=True).start()

# =========================================================
# 🎤 SEND AUDIO (your WAV)
# =========================================================
print("🎤 Streaming audio...")

try:
    wf = wave.open(WAV_FILE, "rb")

    n_channels  = wf.getnchannels()
    sample_rate = wf.getframerate()
    samp_width  = wf.getsampwidth()

    print(f"WAV: {n_channels}ch, {sample_rate}Hz")

    state = None
    CHUNK = 160  # 20ms @ 8kHz

    # 🔇 Send initial silence (important)
    silence = b'\x00' * 320
    for _ in range(10):
        call.write_audio(silence)
        time.sleep(0.02)

    while call.state == CallState.ANSWERED:
        pcm = wf.readframes(CHUNK)
        if not pcm:
            break

        # Stereo → mono
        if n_channels == 2:
            pcm = audioop.tomono(pcm, samp_width, 0.5, 0.5)

        # Resample → 8kHz
        if sample_rate != 8000:
            pcm, state = audioop.ratecv(
                pcm, samp_width, 1, sample_rate, 8000, state
            )

        # Convert → 16-bit
        if samp_width != 2:
            pcm = audioop.lin2lin(pcm, samp_width, 2)

        try:
            call.write_audio(pcm)
        except InvalidStateError:
            print("Call ended during streaming.")
            break
        except Exception as e:
            print("Write error:", e)
            break

        time.sleep(0.02)

    wf.close()
    print("✅ Audio streaming complete.")

except Exception as e:
    print("Audio error:", e)

# ==== WAIT BEFORE HANGUP ====
time.sleep(5)

try:
    call.hangup()
    print("📞 Hung up.")
except:
    print("Call already ended.")

phone.stop()
print("✅ Done.")

import os

print("🎵 Converting to MP3...")

os.system("ffmpeg -y -i received_audio.wav received_audio.mp3")

print("✅ Saved received_audio.mp3")
