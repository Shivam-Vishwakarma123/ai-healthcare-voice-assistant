import { useEffect, useRef, useState } from "react";
import { apiRequest } from "../services/api";
import { useToast } from "./ToastProvider";

export default function VoiceAssistant({ token, language = "en", onNavigate }) {
  const toast = useToast();
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [transcriptionBusy, setTranscriptionBusy] = useState(false);
  const [speechConfig, setSpeechConfig] = useState(null);
  const [speechConfigError, setSpeechConfigError] = useState("");
  const [transcriptNeedsConfirmation, setTranscriptNeedsConfirmation] = useState(false);
  const [error, setError] = useState("");

  // Consent and history state
  const [consentToStore, setConsentToStore] = useState(() => {
    try {
      return localStorage.getItem("carevoice_history_consent") === "true";
    } catch {
      return false;
    }
  });
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);

  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const recordedChunksRef = useRef([]);
  const recordingTimeoutRef = useRef(null);
  const hi = language === "hi";

  useEffect(() => {
    if (!error) return;
    toast(error, "error");
    setError("");
  }, [error, toast]);

  useEffect(() => {
    let active = true;
    apiRequest("/assistant/speech-to-text/config", token)
      .then((config) => {
        if (active) setSpeechConfig(config);
      })
      .catch((reason) => {
        if (active) setSpeechConfigError(reason.message || "Speech input settings could not be loaded.");
      });

    return () => {
      active = false;
      recognitionRef.current?.stop();
      if (mediaRecorderRef.current?.state === "recording") {
        mediaRecorderRef.current.onstop = null;
        mediaRecorderRef.current.stop();
      }
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      window.clearTimeout(recordingTimeoutRef.current);
    };
  }, [token]);

  // Load conversation history if user has consented
  useEffect(() => {
    if (!token || !consentToStore) {
      setConversations([]);
      return;
    }
    let active = true;
    apiRequest("/assistant/conversations", token)
      .then((data) => {
        if (active && Array.isArray(data)) {
          setConversations(data);
        }
      })
      .catch(() => {
        // Silently tolerate if conversations route is unavailable
      });
    return () => {
      active = false;
    };
  }, [token, consentToStore]);

  function handleConsentChange(e) {
    const nextConsent = e.target.checked;
    setConsentToStore(nextConsent);
    try {
      localStorage.setItem("carevoice_history_consent", nextConsent ? "true" : "false");
    } catch {
      // ignore localStorage quota errors
    }
    if (!nextConsent) {
      setActiveConversationId(null);
    }
  }

  async function loadConversation(convId) {
    if (!convId) {
      setActiveConversationId(null);
      setMessages([]);
      return;
    }
    setBusy(true);
    try {
      const data = await apiRequest(`/assistant/conversations/${convId}`, token);
      setActiveConversationId(data.id);
      const loadedMessages = (data.messages || []).map((m) => ({
        role: m.role,
        content: m.content,
        citations: m.citations || [],
        urgency: m.metadata_json?.urgency || "routine",
      }));
      setMessages(loadedMessages);
    } catch (err) {
      setError(err.message || "Could not load consultation transcript.");
    } finally {
      setBusy(false);
    }
  }

  async function clearAllHistory() {
    if (!token) return;
    const confirmed = window.confirm(
      hi
        ? "क्या आप निश्चित रूप से अपना संपूर्ण बातचीत इतिहास हटाना चाहते हैं?"
        : "Are you sure you want to permanently clear all consultation history?"
    );
    if (!confirmed) return;
    setBusy(true);
    try {
      await apiRequest("/assistant/conversations", token, { method: "DELETE" });
      setConversations([]);
      setActiveConversationId(null);
      setMessages([]);
      toast(hi ? "बातचीत इतिहास हटा दिया गया है।" : "Consultation history cleared successfully.", "success");
    } catch (err) {
      setError(err.message || "Could not clear consultation history.");
    } finally {
      setBusy(false);
    }
  }

  function startNewConsultation() {
    setActiveConversationId(null);
    setMessages([]);
    setDraft("");
  }

  async function sendMessage(event) {
    event?.preventDefault();
    const content = draft.trim();
    if (!content || busy || transcriptionBusy || transcriptNeedsConfirmation) return;

    const nextMessages = [...messages, { role: "user", content }];
    setMessages(nextMessages);
    setDraft("");
    setError("");
    setBusy(true);

    try {
      const result = await apiRequest("/assistant/chat", token, {
        method: "POST",
        body: JSON.stringify({
          messages: nextMessages.slice(-20),
          conversation_id: activeConversationId,
          consent_to_store: consentToStore,
        }),
      });

      if (result.conversation_id && !activeConversationId) {
        setActiveConversationId(result.conversation_id);
        // Refresh conversations list
        if (consentToStore && token) {
          apiRequest("/assistant/conversations", token).then((data) => {
            if (Array.isArray(data)) setConversations(data);
          });
        }
      }

      const answer = {
        role: "assistant",
        content: result.reply,
        citations: result.citations || [],
        urgency: result.urgency || "routine",
        recommended_doctors: result.recommended_doctors || [],
      };
      setMessages((current) => [...current, answer]);
    } catch (requestError) {
      setError(requestError.message);
      setMessages((current) => current.slice(0, -1));
      setDraft(content);
    } finally {
      setBusy(false);
    }
  }

  function startListening() {
    setError("");
    if (!speechConfig) {
      setError(
        speechConfigError ||
          (hi ? "वॉइस सेटिंग लोड हो रही हैं। कृपया प्रतीक्षा करें या लिखें।" : "Voice settings are loading. Please wait or type your message.")
      );
      return;
    }
    if (speechConfig.provider !== "browser") {
      void startServerRecording();
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("Voice input is not supported in this browser. Try Chrome, Edge, or type your message.");
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = hi ? "hi-IN" : "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      setDraft(event.results[0][0].transcript);
      setTranscriptNeedsConfirmation(true);
    };
    recognition.onerror = (event) =>
      setError(`Microphone could not transcribe speech (${event.error}). Check browser microphone permission.`);
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    try {
      recognition.start();
    } catch {
      setListening(false);
      setError("Could not start voice capture. Check microphone permission and try again.");
    }
  }

  async function startServerRecording() {
    if (!speechConfig?.transcription_enabled) {
      setError(hi ? "कॉन्फ़िगर किया गया वॉइस प्रदाता उपलब्ध नहीं है। आप लिखकर जारी रख सकते हैं।" : "The configured speech provider is unavailable. You can continue by typing.");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError(hi ? "यह ब्राउज़र रिकॉर्डिंग का समर्थन नहीं करता। कृपया लिखें।" : "This browser cannot record audio. Please type your message.");
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"].find((type) =>
        window.MediaRecorder.isTypeSupported(type)
      );
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      recordedChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) recordedChunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        setError(hi ? "ऑडियो रिकॉर्डिंग विफल हुई। कृपया दोबारा प्रयास करें या लिखें।" : "Audio recording failed. Try again or type your message.");
        recorder.onstop = null;
        if (recorder.state === "recording") recorder.stop();
        stopMediaStream();
        setListening(false);
      };
      recorder.onstop = () => {
        window.clearTimeout(recordingTimeoutRef.current);
        stopMediaStream();
        setListening(false);
        void transcribeRecording(recorder.mimeType || "audio/webm");
      };
      recorder.start();
      setListening(true);
      recordingTimeoutRef.current = window.setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, 60_000);
    } catch {
      stream?.getTracks().forEach((track) => track.stop());
      setListening(false);
      setError(hi ? "माइक्रोफ़ोन शुरू नहीं हो सका। अनुमति जाँचें या लिखें।" : "Could not start the microphone. Check permission or type your message.");
    }
  }

  function stopMediaStream() {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  }

  async function transcribeRecording(mimeType) {
    const audio = new Blob(recordedChunksRef.current, { type: mimeType });
    recordedChunksRef.current = [];
    if (!audio.size) {
      setError(hi ? "कोई ऑडियो रिकॉर्ड नहीं हुआ। कृपया फिर से बोलें या लिखें।" : "No audio was recorded. Try again or type your message.");
      return;
    }
    if (audio.size > speechConfig.max_audio_bytes) {
      setError(hi ? "रिकॉर्डिंग आकार सीमा से बड़ी है। छोटा संदेश रिकॉर्ड करें या लिखें।" : "The recording exceeds the size limit. Record a shorter message or type it.");
      return;
    }
    setTranscriptionBusy(true);
    setError("");
    try {
      const extension = mimeType.includes("ogg") ? "ogg" : mimeType.includes("mp4") ? "mp4" : "webm";
      const form = new FormData();
      form.append("file", audio, `voice.${extension}`);
      form.append("language", hi ? "hi" : "en");
      const result = await apiRequest("/assistant/speech-to-text", token, {
        method: "POST",
        body: form,
      });
      setDraft(result.transcript);
      setTranscriptNeedsConfirmation(result.requires_confirmation);
    } catch (reason) {
      setError(
        reason.message ||
          (hi ? "आवाज़ लिखित रूप में नहीं बदली जा सकी। आप लिखकर जारी रख सकते हैं।" : "Audio could not be transcribed. You can continue by typing.")
      );
    } finally {
      setTranscriptionBusy(false);
    }
  }

  function speak(content) {
    if (!("speechSynthesis" in window)) {
      setError("Speech playback is not supported in this browser.");
      return;
    }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(content));
  }

  return (
    <section className="voice-layout">
      <div className="card voice-card">
        <div className="voice-orb" aria-hidden="true">◉</div>
        <span className="eyebrow">{hi ? "AI वॉइस सहायक" : "AI VOICE ASSISTANT"}</span>
        <h2>{hi ? "आपको किस बारे में मदद चाहिए?" : "What would you like help with?"}</h2>
        <p>
          {hi
            ? "सामान्य स्वास्थ्य जानकारी पूछें या पोर्टल में मदद लें। आपातकालीन लक्षणों की जाँच स्वचालित रूप से पहले होती है।"
            : "Ask general health-information questions or get help navigating the care directory. Deterministic emergency triage pre-screens every inquiry."}
        </p>

        {/* Conversation Consent & Privacy Controls */}
        <div className="cv-conversation-bar">
          <label className="cv-consent-box">
            <input
              type="checkbox"
              checked={consentToStore}
              onChange={handleConsentChange}
              disabled={!token}
            />
            <span>
              {hi
                ? "परामर्श इतिहास सहेजें (सहमति आवश्यक)"
                : "Save consultation history (explicit consent)"}
            </span>
          </label>

          {consentToStore && token && (
            <div className="cv-conversation-actions">
              {conversations.length > 0 && (
                <select
                  className="cv-history-select"
                  value={activeConversationId || ""}
                  onChange={(e) => loadConversation(Number(e.target.value) || null)}
                >
                  <option value="">{hi ? "-- नया सत्र --" : "-- New consultation --"}</option>
                  {conversations.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title} ({new Date(c.updated_at).toLocaleDateString()})
                    </option>
                  ))}
                </select>
              )}
              <button
                type="button"
                className="cv-clear-history-btn"
                onClick={startNewConsultation}
                title="Start a new chat session"
              >
                + {hi ? "नया" : "New"}
              </button>
              {conversations.length > 0 && (
                <button
                  type="button"
                  className="cv-clear-history-btn"
                  onClick={clearAllHistory}
                  title="Clear all saved consultations"
                >
                  🗑️ {hi ? "इतिहास मिटाएँ" : "Clear history"}
                </button>
              )}
            </div>
          )}
        </div>

        {!consentToStore && (
          <div className="disclaimer">
            🔒 {hi ? "गोपनीयता मोड सक्रिय: यह बातचीत CareVoice सर्वर पर सहेजी नहीं जाएगी।" : "Privacy mode active: Conversation is ephemeral and not stored on the server."}
          </div>
        )}

        <div className="disclaimer">
          {hi
            ? "नाम, व्यक्तिगत संपर्क विवरण या पहचान योग्य स्वास्थ्य जानकारी साझा न करें। आपात स्थिति में 112 या 108 डायल करें।"
            : "Do not share personal identifying details. For acute red-flag symptoms, contact emergency services (112, 108, or Tele-MANAS 14416) immediately."}
        </div>
      </div>

      <section className="card chat-card" aria-label="CareVoice conversation">
        <div className="chat-messages" aria-live="polite">
          {!messages.length && (
            <p className="chat-empty">
              {hi
                ? "आपकी बातचीत यहाँ दिखाई देगी। लिखकर या बोलकर शुरू करें।"
                : "Your conversation will appear here. Start by typing or using voice input."}
            </p>
          )}
          {messages.map((message, index) => (
            <article className={`chat-message ${message.role}`} key={`${index}-${message.role}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <b>{message.role === "user" ? (hi ? "आप" : "You") : "CareVoice"}</b>
                {message.role === "assistant" && message.urgency && (
                  <span
                    className={`cv-urgency-badge ${
                      message.urgency === "emergency"
                        ? "emergency"
                        : message.urgency === "urgent"
                        ? "urgent"
                        : "routine"
                    }`}
                  >
                    {message.urgency === "emergency" ? "🚨 Emergency" : message.urgency === "urgent" ? "⚠️ Urgent" : "ℹ️ Guidance"}
                  </span>
                )}
              </div>

              <p>{message.content}</p>

              {/* Expandable citations with provenance and verified source links */}
              {message.role === "assistant" && message.citations?.length > 0 && (
                <details className="chat-citations" open>
                  <summary style={{ cursor: "pointer", fontWeight: "600", color: "var(--cv-accent-text)", marginBottom: "0.5rem" }}>
                    📚 {hi ? "सत्यापित स्रोत साक्ष्य" : "Verified Evidence Sources"} ({message.citations.length})
                  </summary>
                  <ul>
                    {message.citations.map((citation) => (
                      <li key={`${citation.source_url}-${citation.version}`}>
                        <a href={citation.source_url} target="_blank" rel="noreferrer">
                          {citation.title}
                        </a>
                        <span className="cv-source-licence"> · {citation.licence}</span>
                        <br />
                        <small>
                          {citation.provenance} · v{citation.version} · retrieved{" "}
                          {new Date(citation.retrieval_date).toLocaleDateString()}
                        </small>
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              {/* Doctor recommendation cards */}
              {message.role === "assistant" && message.recommended_doctors?.length > 0 && (
                <div className="cv-doctor-recommendations">
                  <div className="cv-doctor-recommendations-title">
                    <span>🩺</span>
                    <span>{hi ? "सुझाए गए सत्यापित चिकित्सक:" : "Recommended Verified Clinicians:"}</span>
                  </div>
                  <div className="cv-doctor-grid">
                    {message.recommended_doctors.map((doc) => (
                      <div key={doc.doctor_id} className="cv-doctor-card">
                        <div className="cv-doctor-card-header">
                          <h4 className="cv-doctor-card-name">Dr. {doc.doctor_name}</h4>
                          <div className="cv-doctor-card-specialty">{doc.specialty}</div>
                          {doc.hospital_name && (
                            <div className="cv-doctor-card-hospital">🏥 {doc.hospital_name}</div>
                          )}
                        </div>
                        {doc.match_reasons?.length > 0 && (
                          <ul className="cv-doctor-card-reasons">
                            {doc.match_reasons.slice(0, 2).map((reason, idx) => (
                              <li key={idx}>{reason}</li>
                            ))}
                          </ul>
                        )}
                        <div className="cv-doctor-card-footer">
                          <span className="cv-doctor-card-fee">
                            ₹{Math.round(doc.fee_minor / 100)}
                          </span>
                          {onNavigate && (
                            <button
                              type="button"
                              className="cv-doctor-book-btn"
                              onClick={() => onNavigate("Find care")}
                            >
                              {hi ? "बुक करें →" : "Book appointment →"}
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {message.role === "assistant" && (
                <button className="text-button" type="button" onClick={() => speak(message.content)}>
                  🔊 {hi ? "ज़ोर से सुनें" : "Read aloud"}
                </button>
              )}
            </article>
          ))}

          {transcriptionBusy && (
            <p className="chat-empty" role="status">
              {hi ? "आवाज़ लिखित रूप में बदली जा रही है…" : "Transcribing audio…"}
            </p>
          )}
          {busy && (
            <p className="chat-empty" role="status">
              {hi ? "CareVoice जवाब तैयार कर रहा है…" : "CareVoice is synthesizing guidance…"}
            </p>
          )}
        </div>

        <form className="chat-form" onSubmit={sendMessage}>
          {transcriptNeedsConfirmation && (
            <div className="notice" role="status">
              {hi
                ? "कृपया ट्रांसक्रिप्ट की समीक्षा करें और पुष्टि करें। आप इसे संपादित कर सकते हैं।"
                : "Review and confirm the voice transcript. You can edit it before sending."}
              <button type="button" onClick={() => setTranscriptNeedsConfirmation(false)}>
                {hi ? "ट्रांसक्रिप्ट की पुष्टि करें" : "Confirm transcript"}
              </button>
            </div>
          )}
          {speechConfigError && (
            <p className="chat-empty">
              {hi
                ? "वॉइस सेटिंग उपलब्ध नहीं हैं; आप लिखकर जारी रख सकते हैं।"
                : "Voice settings are unavailable; you can continue by typing."}
            </p>
          )}
          <textarea
            aria-label={hi ? "संदेश" : "Message"}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={hi ? "सामान्य स्वास्थ्य प्रश्न लिखें…" : "Type a health or portal navigation question…"}
            maxLength={4000}
            rows={2}
          />
          <div className="chat-actions">
            <button
              className="secondary"
              type="button"
              onClick={
                listening
                  ? () => {
                      if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
                      else recognitionRef.current?.stop();
                    }
                  : startListening
              }
              disabled={busy || transcriptionBusy}
            >
              {listening
                ? hi
                  ? "सुनना बंद करें"
                  : "Stop listening"
                : hi
                ? "🎙 बोलकर पूछें"
                : "🎙 Use voice"}
            </button>
            <button
              className="primary"
              type="submit"
              disabled={busy || transcriptionBusy || transcriptNeedsConfirmation || !draft.trim()}
            >
              {busy
                ? hi
                  ? "भेज रहे हैं…"
                  : "Sending…"
                : hi
                ? "संदेश भेजें →"
                : "Send message →"}
            </button>
          </div>
        </form>
      </section>
    </section>
  );
}
