import { useEffect, useRef, useState } from "react";
import { apiRequest } from "../services/api";
import { useToast } from "./ToastProvider";

const QUICK_PROMPTS = [
  {
    en: "I have had a mild fever and body ache for 2 days",
    hi: "मुझे 2 दिन से हल्का बुखार और बदन दर्द है",
    labelEn: "🌡️ Fever for 2 days",
    labelHi: "🌡️ 2 दिन से बुखार",
  },
  {
    en: "Experiencing persistent dry cough and throat irritation",
    hi: "लगातार सूखी खांसी और गले में खराश हो रही है",
    labelEn: "🗣️ Persistent dry cough",
    labelHi: "🗣️ सूखी खांसी",
  },
  {
    en: "How do I book an appointment with Dr. Asha in General Medicine?",
    hi: "जनरल मेडिसिन में डॉ. आशा के साथ अपॉइंटमेंट कैसे बुक करें?",
    labelEn: "📅 Book Dr. Asha",
    labelHi: "📅 डॉ. आशा से अपॉइंटमेंट",
  },
  {
    en: "What should I do if blood pressure readings are higher than normal?",
    hi: "यदि रक्तचाप सामान्य से अधिक आए तो क्या प्राथमिक कदम उठाने चाहिए?",
    labelEn: "🩺 High blood pressure advice",
    labelHi: "🩺 उच्च रक्तचाप मार्गदर्शन",
  },
];

function assistantErrorMessage(message, hindi) {
  const detail = String(message || "");
  if (/ollama|model.{0,80}(not downloaded|not found)|not downloaded.{0,80}model/i.test(detail)) {
    return hindi
      ? "AI सेवा अभी उपलब्ध नहीं है। सुरक्षा जाँच का परिणाम उपलब्ध है; कृपया बाद में फिर प्रयास करें।"
      : "The AI service is temporarily unavailable. Your safety-check result remains available; please try again later.";
  }
  return detail || (hindi ? "संदेश भेजा नहीं जा सका। कृपया फिर प्रयास करें।" : "Your message could not be sent. Please try again.");
}

function renderFormattedContent(text) {
  if (!text) return null;
  const lines = text.split("\n");
  const elements = [];
  let currentList = [];
  let listType = null;

  function flushList() {
    if (currentList.length > 0) {
      if (listType === "ol") {
        elements.push(<ol key={`ol-${elements.length}`} className="cv-message-list ol">{currentList}</ol>);
      } else {
        elements.push(<ul key={`ul-${elements.length}`} className="cv-message-list ul">{currentList}</ul >);
      }
      currentList = [];
      listType = null;
    }
  }

  function formatInline(str) {
    const parts = str.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      }
      return part;
    });
  }

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }

    const numMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
    if (numMatch) {
      if (listType !== "ol") flushList();
      listType = "ol";
      currentList.push(<li key={`li-${idx}`}>{formatInline(numMatch[2])}</li>);
      return;
    }

    const bulletMatch = trimmed.match(/^[-*•]\s+(.*)$/);
    if (bulletMatch) {
      if (listType !== "ul") flushList();
      listType = "ul";
      currentList.push(<li key={`li-${idx}`}>{formatInline(bulletMatch[1])}</li>);
      return;
    }

    flushList();
    elements.push(
      <p key={`p-${idx}`} className="cv-message-paragraph">
        {formatInline(trimmed)}
      </p>
    );
  });

  flushList();
  return <div className="cv-message-body">{elements}</div>;
}

// Interactive AI voice and text health assistant providing clinical triage, RAG evidence citations, and doctor discovery.
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
  const [lastFailedPrompt, setLastFailedPrompt] = useState("");

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
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const hi = language === "hi";

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy, transcriptionBusy]);

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

  // Updates user consent for conversation transcript persistence under DPDP Act 2023.
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

  // Fetches a prior consultation session transcript with clinical citations and urgency classification.
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

  // Permanently clears all saved user consultation history from client state and backend database.
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

  // Resets active conversation thread to start a clean triage and medical information consultation.
  function startNewConsultation() {
    setActiveConversationId(null);
    setMessages([]);
    setDraft("");
    setLastFailedPrompt("");
  }

  // Dispatches user prompt to AI assistant with triage classification, RAG retrieval, and recommendation extraction.
  async function sendMessage(event, textOverride = null) {
    event?.preventDefault();
    const content = (textOverride !== null ? textOverride : draft).trim();
    if (!content || busy || transcriptionBusy || transcriptNeedsConfirmation) return;

    const nextMessages = [...messages, { role: "user", content }];
    setMessages(nextMessages);
    setDraft("");
    setError("");
    setLastFailedPrompt("");
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
        conflicting_sources: result.conflicting_sources || result.source_conflict || false,
        insufficient_reference_material: result.insufficient_reference_material || false,
        precautionary_escalation_note: result.precautionary_escalation_note || null,
        retrieval_confidence: result.retrieval_confidence ?? null,
      };
      setMessages((current) => [...current, answer]);
      setLastFailedPrompt("");
    } catch (requestError) {
      setError(assistantErrorMessage(requestError.message, hi));
      setLastFailedPrompt(content);
      setMessages((current) => current.slice(0, -1));
      setDraft(content);
    } finally {
      setBusy(false);
    }
  }

  async function copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast(hi ? "मार्गदर्शन कॉपी किया गया।" : "Response copied to clipboard.", "success");
    } catch {
      toast("Could not copy text.", "error");
    }
  }

  function downloadTranscript() {
    if (!messages.length) return;
    const header = `CareVoice AI Health Consultation Summary\nDate: ${new Date().toLocaleString()}\nLanguage: ${language}\nNotice: General health education only. Not a medical diagnosis.\nEmergency: Call 112 or 108 immediately if in danger.\n\n========================================\n\n`;
    const transcriptText = messages
      .map((m) => `[${m.role === "user" ? (hi ? "मरीज़" : "Patient") : "CareVoice Assistant"}]:\n${m.content}\n`)
      .join("\n----------------------------------------\n\n");
    const blob = new Blob([header + transcriptText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `carevoice-consultation-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast(hi ? "सारांश डाउनलोड किया गया।" : "Consultation summary downloaded.", "success");
  }

  function handleQuickPrompt(promptText) {
    setDraft(promptText);
    textareaRef.current?.focus();
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!busy && !transcriptionBusy && !transcriptNeedsConfirmation && draft.trim()) {
        sendMessage(event);
      }
    }
  }

  function retryLastFailed() {
    if (lastFailedPrompt) {
      const promptToRetry = lastFailedPrompt;
      setLastFailedPrompt("");
      sendMessage(null, promptToRetry);
    }
  }

  // Initiates microphone capture routing to browser Web Speech API or server-side Whisper transcription.
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

  // Records audio chunks via MediaRecorder API for upstream backend speech-to-text transcription.
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

  // Releases hardware microphone media stream tracks when voice capture terminates.
  function stopMediaStream() {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  }

  // Sends audio binary payload to backend speech-to-text endpoint for clinical transcription.
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

  // Synthesizes voice assistant text responses into spoken audio using browser SpeechSynthesis API.
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
        <div className="cv-chat-card-header">
          <span className="cv-chat-card-title">💬 {hi ? "परामर्श बातचीत" : "Consultation Thread"}</span>
          {messages.length > 0 && (
            <div className="cv-chat-card-tools">
              <button
                type="button"
                className="cv-chat-tool-btn"
                onClick={downloadTranscript}
                title={hi ? "परामर्श सारांश डाउनलोड करें" : "Download consultation transcript"}
              >
                📥 {hi ? "सारांश डाउनलोड" : "Download summary"}
              </button>
              <button
                type="button"
                className="cv-chat-tool-btn"
                onClick={startNewConsultation}
                title={hi ? "नई बातचीत शुरू करें" : "Start fresh session"}
              >
                + {hi ? "नया" : "New"}
              </button>
            </div>
          )}
        </div>

        <div className="chat-messages" aria-live="polite">
          {!messages.length && (
            <div className="chat-empty-container">
              <p className="chat-empty">
                {hi
                  ? "आपकी बातचीत यहाँ दिखाई देगी। एक त्वरित विषय चुनें या अपना प्रश्न लिखें।"
                  : "Your conversation will appear here. Choose a quick topic below or type your question."}
              </p>
              <div className="cv-quick-prompts" aria-label={hi ? "त्वरित सुझाव" : "Quick suggestions"}>
                <div className="cv-quick-prompts-title">
                  💡 {hi ? "सुझाए गए प्रश्न" : "Suggested questions"}
                </div>
                <div className="cv-quick-prompts-grid">
                  {QUICK_PROMPTS.map((qp, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className="cv-quick-prompt-btn"
                      onClick={() => handleQuickPrompt(hi ? qp.hi : qp.en)}
                    >
                      <span>{qp.icon}</span>
                      <span>{hi ? qp.hi : qp.en}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
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

              {message.role === "assistant" ? (
                renderFormattedContent(message.content)
              ) : (
                <p className="cv-message-paragraph">{message.content}</p>
              )}

              {/* Module 4: Conflicting Clinical Guidance Alert */}
              {message.role === "assistant" && message.conflicting_sources && (
                <div className="cv-alert cv-alert-warning" style={{ margin: "8px 0" }}>
                  <div style={{ fontWeight: "700" }}>⚠️ Conflicting Clinical Guidance Detected:</div>
                  <div style={{ fontSize: "0.88rem", marginTop: "2px" }}>
                    Retrieved public-health sources provide differing urgent-care or triage recommendations. CareVoice does not select or synthesize conflicting guidance. Please consult a qualified clinician immediately, or call 112/108 if symptoms worsen.
                  </div>
                </div>
              )}

              {/* Module 4: Insufficient Reference Material Notice */}
              {message.role === "assistant" && message.insufficient_reference_material && (
                <div className="cv-alert cv-alert-warning" style={{ margin: "8px 0", background: "var(--cv-surface-tint)", borderColor: "var(--cv-accent-soft)" }}>
                  <div style={{ fontWeight: "700" }}>ℹ️ Clinical Reference Gap (Threshold &lt; 0.45):</div>
                  <div style={{ fontSize: "0.88rem", marginTop: "2px" }}>
                    No verified public-health source reached the required clinical evidence threshold for this query. This response is limited to general educational orientation, not clinical guidance.
                  </div>
                </div>
              )}

              {/* Module 4: Precautionary Escalation Note */}
              {message.role === "assistant" && message.precautionary_escalation_note && (
                <div style={{ padding: "8px 12px", background: "var(--cv-surface-soft)", borderRadius: "6px", margin: "8px 0", fontSize: "0.85rem", borderLeft: "3px solid var(--cv-accent)" }}>
                  <strong>Precautionary Escalation:</strong> {message.precautionary_escalation_note}
                </div>
              )}

              {/* Expandable Clinical Evidence & Uncertainty Panel */}
              {message.role === "assistant" && message.citations?.length > 0 && (
                <details className="chat-citations" open>
                  <summary style={{ cursor: "pointer", fontWeight: "600", color: "var(--cv-accent-text)", marginBottom: "0.5rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span>📚 {hi ? "सत्यापित स्रोत साक्ष्य व अनिश्चितता" : "Clinical Evidence & Uncertainty"} ({message.citations.length})</span>
                    {message.retrieval_confidence !== null && message.retrieval_confidence !== undefined && (
                      <span className={`cv-badge ${message.retrieval_confidence >= 0.45 ? "cv-badge-routine" : "cv-badge-urgent"}`} style={{ fontSize: "0.75rem" }}>
                        Confidence: {(message.retrieval_confidence * 100).toFixed(0)}%
                      </span>
                    )}
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
                <div className="cv-message-actions">
                  <button
                    className="cv-message-action-btn"
                    type="button"
                    onClick={() => speak(message.content)}
                    title={hi ? "ज़ोर से सुनें" : "Read aloud"}
                  >
                    🔊 {hi ? "सुनें" : "Read aloud"}
                  </button>
                  <button
                    className="cv-message-action-btn"
                    type="button"
                    onClick={() => copyToClipboard(message.content)}
                    title={hi ? "मार्गदर्शन कॉपी करें" : "Copy to clipboard"}
                  >
                    📋 {hi ? "कॉपी" : "Copy"}
                  </button>
                </div>
              )}
            </article>
          ))}

          {messages.length > 0 && messages[messages.length - 1].urgency === "emergency" && (
            <aside className="cv-chat-emergency-banner" role="alert">
              <div>
                <strong>🚨 {hi ? "आपातकालीन चेतावनी: तत्काल सहायता प्राप्त करें" : "Emergency Alert: Immediate Care Required"}</strong>
                <div style={{ fontSize: "12px", marginTop: "2px" }}>
                  {hi
                    ? "पहचाने गए लक्षणों के लिए तत्काल आपातकालीन मूल्यांकन आवश्यक हो सकता है।"
                    : "The symptoms described may represent an acute emergency. Contact emergency services right away."}
                </div>
              </div>
              <div className="cv-chat-emergency-links">
                <a href="tel:112" className="cv-chat-emergency-btn">📞 112</a>
                <a href="tel:108" className="cv-chat-emergency-btn">🚑 108</a>
                <a href="tel:14416" className="cv-chat-emergency-btn">🧠 14416</a>
              </div>
            </aside>
          )}

          {lastFailedPrompt && (
            <aside className="cv-chat-retry-banner" role="status">
              <div className="cv-chat-retry-content">
                <span>
                  ⚠️ {hi ? "पिछला संदेश भेजने में असमर्थ रहा।" : "Unable to reach CareVoice AI. You can retry with one click."}
                </span>
                <div className="cv-chat-retry-buttons">
                  <button
                    type="button"
                    className="cv-button cv-button-primary cv-btn-sm"
                    onClick={retryLastFailed}
                    disabled={busy}
                  >
                    🔄 {hi ? "पुनः प्रयास करें" : "Retry now"}
                  </button>
                </div>
              </div>
            </aside>
          )}

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
          <div ref={messagesEndRef} />
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
            ref={textareaRef}
            aria-label={hi ? "संदेश" : "Message"}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={hi ? "सामान्य स्वास्थ्य प्रश्न लिखें… (Enter दबाएँ भेजने के लिए)" : "Type a health question… (Press Enter to send, Shift+Enter for new line)"}
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
